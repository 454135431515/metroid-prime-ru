"""Прогон на вылеты: порт с модом по очереди загружает каждую комнату каждого мира.

    python -I tools/crawl.py <ISO> <AppRun порта> <папка модов> <отчёт.tsv> [--frames N] [--only MLVL]

Порт запускается с отдельной user-папкой (work/user-crawl — копия work/user без быстрого
продолжения; сохранения владельца не трогаются, карта памяти только читается) и консолью
MP_CONSOLE. Игра загружается со слота A, дальше `warp <MLVL> <MREA>` в каждую комнату и
N кадров ожидания. Вылет = порт перестал отвечать: строка в отчёте, хвост лога, перезапуск,
продолжение со следующей комнаты. Ошибки загрузки ресурсов (`failed to load`, `Truncated`)
пишутся в отчёт, даже если порт не упал.
"""

import os
import shutil
import socket
import struct
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mp  # noqa: E402

PORT = 4777
USER = "work/user-crawl"
BAD = ("crashed", "Truncated", "failed to load", "uncaught", "SIGSEGV", "SIGABRT")


def worlds(iso_path):
    """[(MLVL, [MREA...])] в порядке PAK диска."""
    out = []
    with open(iso_path, "rb") as iso:
        for name, off, size in mp.disc_files(iso):
            low = name.lower()
            if not (low.startswith("metroid") and low.endswith(".pak")):
                continue
            iso.seek(off)
            res = list(mp.pak_resources(iso.read(size)))
            mlvl = [rid for typ, rid, _ in res if typ == "MLVL"]
            if mlvl:
                out.append((mlvl[0], [rid for typ, rid, _ in res if typ == "MREA"]))
    return out


class Console:
    def __init__(self):
        self.s = None

    def connect(self, wait):
        end = time.monotonic() + wait
        while True:
            try:
                self.s = socket.create_connection(("127.0.0.1", PORT), timeout=120)
                self.f = self.s.makefile("r", encoding="utf-8", errors="replace")
                return True
            except OSError:
                if time.monotonic() > end:
                    return False
                time.sleep(1)

    def cmd(self, line):
        """Ответ команды до «=> ok|err»; None — порт не отвечает."""
        try:
            self.s.sendall((line + "\n").encode())
            out = []
            for row in self.f:
                if row.startswith("=> "):
                    return "".join(out), row.startswith("=> ok")
                out.append(row)
        except OSError:
            pass
        return None


def start(apprun, mods, iso):
    if os.path.isdir(USER):
        shutil.rmtree(USER)
    shutil.copytree("work/user", USER)
    resume = os.path.join(USER, "savestates", "resume.mpss")
    if os.path.exists(resume):
        os.remove(resume)
    env = dict(os.environ, MP_USER_PATH=USER, MP_MODS=mods, MP_CONSOLE=str(PORT), SDL_AUDIO_DRIVER="dummy")
    proc = subprocess.Popen([apprun, iso], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    con = Console()
    if not con.connect(90):
        return proc, None
    con.cmd("wait 400")
    con.cmd("press start 5")
    con.cmd("wait 500")
    for _ in range(10):  # слот A: ждём, пока игра пойдёт
        con.cmd("press a 5")
        con.cmd("wait 300")
        r = con.cmd("status")
        if r and r[1]:
            return proc, con
    return proc, None


def log_tail(n=40):
    path = os.path.join(USER, "metroid_prime_port.log")
    if not os.path.isfile(path):
        return []
    return open(path, encoding="utf-8", errors="replace").read().splitlines()[-n:]


def log_size():
    path = os.path.join(USER, "metroid_prime_port.log")
    return os.path.getsize(path) if os.path.isfile(path) else 0


def new_bad(since):
    path = os.path.join(USER, "metroid_prime_port.log")
    with open(path, "rb") as f:
        f.seek(since)
        text = f.read().decode("utf-8", "replace")
    return [ln for ln in text.splitlines() if any(b in ln for b in BAD)]


def main(iso, apprun, mods, report, *opts):
    frames = int(opts[opts.index("--frames") + 1]) if "--frames" in opts else 180
    only = opts[opts.index("--only") + 1].upper() if "--only" in opts else None
    plan = [(w, a) for w, areas in worlds(iso) for a in areas if not only or f"{w:08X}" == only]
    rows = []
    proc, con = start(apprun, mods, iso)
    i = 0
    while i < len(plan):
        w, a = plan[i]
        key = f"{w:08X}\t{a:08X}"
        if con is None:
            rows.append(f"{key}\tне стартовал\t" + " | ".join(log_tail(5)))
            proc.kill()
            proc, con = start(apprun, mods, iso)
            i += 1
            continue
        mark = log_size()
        r = con.cmd(f"warp {w:08X} {a:08X}")
        r2 = con.cmd(f"wait {frames}") if r else None
        alive = r2 is not None and proc.poll() is None
        bad = new_bad(mark) if os.path.isfile(os.path.join(USER, "metroid_prime_port.log")) else []
        if not alive:
            rows.append(f"{key}\tВЫЛЕТ\t" + " | ".join(log_tail(25)))
            print(f"[{i + 1}/{len(plan)}] {key} ВЫЛЕТ", flush=True)
            proc.kill()
            proc.wait()
            proc, con = start(apprun, mods, iso)
        else:
            status = "ok" if r and r[1] else "warp: " + (r[0].strip()[:120] if r else "нет ответа")
            rows.append(f"{key}\t{status}\t" + " | ".join(bad[:5]))
            if bad or status != "ok":
                print(f"[{i + 1}/{len(plan)}] {key} {status} {bad[:2]}", flush=True)
        i += 1
        if i % 25 == 0:
            print(f"[{i}/{len(plan)}]", flush=True)
            open(report, "w", encoding="utf-8").write("mlvl\tmrea\tрезультат\tлог\n" + "\n".join(rows) + "\n")
    if con:
        con.cmd("quit")
    time.sleep(3)
    if proc.poll() is None:
        proc.kill()
    open(report, "w", encoding="utf-8").write("mlvl\tmrea\tрезультат\tлог\n" + "\n".join(rows) + "\n")
    crashes = sum("\tВЫЛЕТ\t" in r for r in rows)
    print(f"crawl: {len(rows)} комнат, вылетов {crashes}, с ошибками ресурсов "
          f"{sum(1 for r in rows if r.split(chr(9))[3:4] != [''])} -> {report}")


if __name__ == "__main__":
    main(*sys.argv[1:])
