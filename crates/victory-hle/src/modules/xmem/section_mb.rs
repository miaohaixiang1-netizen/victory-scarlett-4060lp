//! Split large physical-page allocations into smaller section objects.
//!
//! Windows can spend long periods walking thousands of mapped views while
//! holding one section's lock. GTA's large physical-page request can collect
//! over a hundred thousand views. Smaller sections bound that shared lock's
//! scope; page numbers remain consecutive and callers still see one request.
use super::*;

/// Maximum pages per section; `usize::MAX` keeps the historical one-section
/// behavior when the switch is unset, zero, or invalid.
pub(super) fn section_pages() -> usize {
    static PAGES: LazyLock<usize> = LazyLock::new(|| {
        let pages = pages_per_section(std::env::var("VICTORY_SECTION_MB").ok().as_deref());
        if pages != usize::MAX {
            tracing::info!(mb = pages * PAGE / MIB, pages, "physical pages split into bounded sections (VICTORY_SECTION_MB)");
        }
        pages
    });
    *PAGES
}

fn pages_per_section(mb: Option<&str>) -> usize {
    mb.and_then(|value| value.trim().parse::<usize>().ok())
        .map(|mb| mb.saturating_mul(MIB / PAGE))
        .filter(|&pages| pages != 0)
        .unwrap_or(usize::MAX)
}

/// Make `n` physical pages in sections of at most `per`, number them as one
/// contiguous allocation, and add every page to the title's physical table.
fn allocate(n: usize, per: usize) -> std::io::Result<usize> {
    if n.checked_mul(PAGE).is_none_or(|size| size == 0) {
        return Err(std::io::ErrorKind::InvalidInput.into());
    }
    let per = per.max(1);
    let mut sections = Vec::<Arc<Section>>::with_capacity(n.div_ceil(per));
    let mut made = 0;
    while made < n {
        let pages = per.min(n - made);
        let size = pages * PAGE;
        // SAFETY: creates a pagefile-backed section of the requested size.
        let handle = unsafe {
            CreateFileMappingW(
                INVALID_HANDLE_VALUE,
                std::ptr::null(),
                PAGE_READWRITE | if on_wine() { SEC_COMMIT } else { SEC_RESERVE },
                (size as u64 >> 32) as u32,
                size as u32,
                std::ptr::null(),
            )
        };
        if handle.is_null() {
            return Err(std::io::Error::last_os_error());
        }
        sections.push(Arc::new(Section {
            handle,
            pages,
            window: std::sync::OnceLock::new(),
            committed: (0..pages.div_ceil(64)).map(|_| std::sync::atomic::AtomicU64::new(0)).collect(),
            resident: (0..pages.div_ceil(64)).map(|_| std::sync::atomic::AtomicU64::new(0)).collect(),
            discarded: (0..pages.div_ceil(64)).map(|_| std::sync::atomic::AtomicU64::new(0)).collect(),
        }));
        made += pages;
    }

    for section in &sections {
        victory_gpu::title_memory_section(section.handle as usize, (section.pages * PAGE) as u64, on_wine());
    }
    let mut table = page_table_mut();
    let first = table.next_page;
    table.next_page += n * FRAMES;
    let mut number = first;
    for section in &sections {
        for index in 0..section.pages {
            table.pages.insert(number, Slice { section: section.clone(), index });
            number += FRAMES;
        }
    }
    TITLE_PAGES.fetch_add(n * PAGE, Ordering::Relaxed);
    Ok(first)
}

pub(super) fn allocate_physical(n: usize, per: usize) -> std::io::Result<usize> {
    allocate(n, per)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn section_size_switch_uses_whole_mebibytes_and_defaults_to_one() {
        for value in [None, Some(""), Some("0"), Some("bad"), Some("-2")] {
            assert_eq!(pages_per_section(value), usize::MAX, "{value:?}");
        }
        assert_eq!(pages_per_section(Some("1")), 16);
        assert_eq!(pages_per_section(Some(" 2 ")), 32);
        assert_eq!(pages_per_section(Some("999999999999999999999999999999")), usize::MAX);
        assert!(allocate(0, 32).is_err());
    }

    #[test]
    fn physical_pages_are_numbered_contiguously_across_section_boundaries() {
        let pages = 70;
        let first = allocate(pages, 32).expect("physical pages allocated");
        let table = page_table();
        let slices: Vec<_> = (0..pages)
            .map(|index| table.pages.get(&(first + index * FRAMES)).expect("page entered").clone())
            .collect();
        assert!(slices.iter().enumerate().all(|(index, slice)| slice.index == index % 32));
        assert!(Arc::ptr_eq(&slices[0].section, &slices[31].section));
        assert!(!Arc::ptr_eq(&slices[31].section, &slices[32].section));
        assert_eq!(slices[0].section.pages, 32);
        assert_eq!(slices[64].section.pages, 6);
        drop(table);

        let ids: Vec<_> = (0..pages).map(|index| first + index * FRAMES).collect();
        let groups = runs(&ids, 0, pages * PAGE).expect("all pages exist");
        assert_eq!(groups.iter().map(|(_, count)| *count).collect::<Vec<_>>(), [32, 32, 6]);

        // A write crossing a section boundary cannot use one large view, but
        // the normal per-section write path must still place every byte.
        let offset = 30 * PAGE + 7;
        let data: Vec<_> = (0..3 * PAGE + 19).map(|index| (index % 251) as u8).collect();
        assert!(page_window(&ids, offset, data.len()).is_none());
        assert!(write_physical(&ids, offset, &data));
        let written: Vec<u8> = ids[30..35]
            .iter()
            .flat_map(|page| {
                let slice = page_table().pages.get(page).expect("page exists").clone();
                View::map(&slice, 1).expect("page can be read").bytes().to_vec()
            })
            .collect();
        assert_eq!(&written[7..7 + data.len()], data.as_slice());

        assert_eq!(XMemFreePhysicalPages(pages, ids.as_ptr()), 1);
    }
}
