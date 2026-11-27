import msvcrt, os, re, shlex, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT / '\u91cd\u7f16\u8bd1\u8d44\u6599'
CONFIG = BASE / 'launch_scarlett_8gb_native1080.sh'
EXE = BASE / 'repos' / 'victory-scarlett-3070' / 'target' / 'diag' / 'victory.exe'
HUD = BASE / 'hud.py'
GAME = ROOT / 'GTA6.v1.0.2.1-CYBERLEEK\uff08\u6e38\u620f\u672c\u4f53\uff09' / 'game_scarlett_master.exe'

def main():
    for p in (CONFIG, EXE, HUD, GAME):
        if not p.is_file():
            raise FileNotFoundError(str(p))
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('VICTORY_')}
    for line in CONFIG.read_text(encoding='utf-8').splitlines():
        m = re.fullmatch(r'export (VICTORY_[A-Z0-9_]+)=(.*)', line.strip())
        if m and m.group(1) != 'VICTORY_AUTO_INPUT':
            values = shlex.split(m.group(2), comments=True, posix=True)
            if len(values) != 1:
                raise ValueError('Invalid setting: ' + line)
            env[m.group(1)] = values[0]
    env['VICTORY_AUTO_INPUT'] = 'A'
    env['VICTORY_AUTO_INPUT_START_S'] = '15'
    for name in ('VICTORY_GAME_DIR', 'VICTORY_CACHE_DIR', 'VICTORY_DATA_DIR'):
        if not Path(env[name]).is_dir():
            raise FileNotFoundError(name + ': ' + env[name])
    if '--check' in sys.argv:
        print('Configuration and required files OK; one gamepad A at 15s; native 1080p; HUD enabled.')
        return
    lock = (BASE / 'ab' / 'game-cache.lock').open('a+b')
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        raise RuntimeError('Game or cache warming is already running from this launcher.')
    log = BASE / 'ab' / ('manual-' + time.strftime('%Y%m%d-%H%M%S') + '-' + str(os.getpid()) + '.log')
    print('Game log:', log, flush=True)
    with log.open('wb') as output:
        game = subprocess.Popen([str(EXE), 'run', str(GAME), '--execute', '--console', 'series-s'], cwd=str(EXE.parent.parent.parent), env=env, stdout=output, stderr=subprocess.STDOUT)
        monitor = subprocess.Popen([sys.executable, str(BASE / 'repos' / 'victory-scarlett-3070' / 'tools' / 'session-monitor.py'), str(game.pid), str(log.with_name(log.stem + '-metrics.csv'))], cwd=str(BASE), creationflags=0x08000000)
        hud = None
        try:
            hud_log = log.with_name(log.stem + '-hud.log')
            with hud_log.open('wb') as hud_output:
                hud = subprocess.Popen([sys.executable, str(HUD), str(log), str(game.pid), "--exit-with-game"], cwd=str(BASE), stdout=hud_output, stderr=subprocess.STDOUT)
            time.sleep(2)
            if hud.poll() is not None:
                print('HUD exited unexpectedly. Details:', hud_log, flush=True)
            else:
                print('Game and HUD started. Close the game window to exit.', flush=True)
            code = game.wait()
            print('Game exited with code', code, flush=True)
        finally:
            if hud and hud.poll() is None:
                hud.terminate()
            try:
                monitor.wait(timeout=10)
            except subprocess.TimeoutExpired:
                monitor.terminate()
    if code is not None:
        warm_log = log.with_name(log.stem + '-warm.log')
        print('Warming used pipelines; all recorded pipelines remain saved; please keep this window open. Log:', warm_log, flush=True)
        with warm_log.open('wb') as output:
            warm = subprocess.run([str(EXE), 'warm', '--used', '--jobs', '8'], cwd=str(EXE.parent.parent.parent), env=env, stdout=output, stderr=subprocess.STDOUT)
        print('Pipeline warm exit code:', warm.returncode, flush=True)
        if warm.returncode:
            print('Warm incomplete; existing cache and recorded pipelines are retained.', flush=True)
            input('Press Enter to close...')
    if code:
        print('See the log for details.', flush=True)
        input('Press Enter to close...')

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('Launch error:', e, flush=True)
        if '--check' not in sys.argv:
            input('Press Enter to close...')
        sys.exit(1)
