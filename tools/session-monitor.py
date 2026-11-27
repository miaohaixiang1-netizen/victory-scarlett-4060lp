import csv, ctypes, subprocess, sys, time
from datetime import datetime
pid=int(sys.argv[1]); path=sys.argv[2]
k=ctypes.WinDLL('kernel32',use_last_error=True); k.OpenProcess.restype=ctypes.c_void_p; k.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32]; k.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32]; k.WaitForSingleObject.restype=ctypes.c_uint32
h=k.OpenProcess(0x101000,False,pid)
if not h: sys.exit(1)
psapi=ctypes.WinDLL('psapi',use_last_error=True)
class ProcessMemory(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('page_faults',ctypes.c_ulong),('peak_working_set',ctypes.c_size_t),('working_set',ctypes.c_size_t),('peak_paged_pool',ctypes.c_size_t),('paged_pool',ctypes.c_size_t),('peak_nonpaged_pool',ctypes.c_size_t),('nonpaged_pool',ctypes.c_size_t),('pagefile',ctypes.c_size_t),('peak_pagefile',ctypes.c_size_t),('private_usage',ctypes.c_size_t)]
psapi.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.POINTER(ProcessMemory),ctypes.c_ulong]; psapi.GetProcessMemoryInfo.restype=ctypes.c_int
with open(path,'w',newline='',encoding='utf8') as f:
 w=csv.writer(f);w.writerow(['time','gpu_percent','vram_used_mib','power_w','gpu_temp_c','ram_available_mib','game_working_set_mib','game_private_mib','game_page_faults']);f.flush()
 class Memory(ctypes.Structure):
  _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),('total',ctypes.c_ulonglong),('available',ctypes.c_ulonglong),('totalpage',ctypes.c_ulonglong),('availablepage',ctypes.c_ulonglong),('totalvirt',ctypes.c_ulonglong),('availablevirt',ctypes.c_ulonglong),('availableextended',ctypes.c_ulonglong)]
 while True:
  m=Memory();m.length=ctypes.sizeof(m);k.GlobalMemoryStatusEx(ctypes.byref(m))
  pm=ProcessMemory();pm.cb=ctypes.sizeof(pm)
  game_mem=[round(pm.working_set/1048576),round(pm.private_usage/1048576),pm.page_faults] if psapi.GetProcessMemoryInfo(h,ctypes.byref(pm),pm.cb) else ['','','']
  try:
   r=subprocess.run(['nvidia-smi','--query-gpu=utilization.gpu,memory.used,power.draw,temperature.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=8,creationflags=0x08000000); vals=next(csv.reader(r.stdout.splitlines()),[])
  except (OSError,subprocess.SubprocessError): vals=[]
  w.writerow([datetime.now().isoformat(timespec='seconds'),*(vals[:4] if len(vals)>=4 else ['','','','']),round(m.available/1048576),*game_mem]);f.flush()
  if k.WaitForSingleObject(h,30000)!=0x102:break
k.CloseHandle.argtypes=[ctypes.c_void_p];k.CloseHandle(h)
