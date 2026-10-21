"""work/res/STRG + work/inventory.tsv + work/scans.tsv -> text/en.json.

    python -I tools/dump_en.py work text/en.json

{ "<STRG id>": { "paks": [...], "name": "...", "kind": "scan|ui|world",
                 "category": <логбук, только у сканов>, "strings": [...] } }
kind: scan — таблица скана; ui — живёт в общих PAK (меню, HUD, подборы);
world — прочее из PAK регионов (надписи терминалов, подсказки).
"""

import csv
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strg  # noqa: E402

SHARED = {"MiscData.pak", "NoARAM.pak", "GGuiSys.pak", "AudioGrp.pak", "MidiData.pak",
          "SamGunFx.pak", "SamusGun.pak", "TestAnim.pak", "SlideShow.pak"}
REGIONS = {  # PAK (в нижнем регистре: на диске есть и metroid5.pak) -> регион, для порядка тикетов перевода
    "metroid1.pak": "Space Pirate Frigate", "metroid2.pak": "Chozo Ruins",
    "metroid3.pak": "Phendrana Drifts", "metroid4.pak": "Tallon Overworld",
    "metroid5.pak": "Phazon Mines", "metroid6.pak": "Magmoor Caverns",
    "metroid7.pak": "Impact Crater", "metroid8.pak": "End Cinema",
}


def main(work, out):
    info = {}
    with open(os.path.join(work, "inventory.tsv")) as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r["type"] == "STRG":
                e = info.setdefault(r["id"], {"paks": [], "name": ""})
                e["paks"].append(r["pak"])
                e["name"] = e["name"] or r["name"]
    scans = {}
    with open(os.path.join(work, "scans.tsv")) as f:
        for r in csv.DictReader(f, delimiter="\t"):
            scans[r["strg"]] = int(r["category"])
    tables = {}
    for p in sorted(glob.glob(os.path.join(work, "res", "STRG", "*.STRG"))):
        sid = os.path.basename(p)[:8]
        (lang, strings), = strg.parse(open(p, "rb").read())
        e = info[sid]
        if sid in scans:
            kind = "scan"
        elif any(pk in SHARED for pk in e["paks"]):
            kind = "ui"
        else:
            kind = "world"
        t = {"paks": sorted(set(e["paks"])), "regions": sorted({REGIONS[pk.lower()] for pk in e["paks"] if pk.lower() in REGIONS}),
             "name": e["name"], "kind": kind, "strings": strings}
        if sid in scans:
            t["category"] = scans[sid]
        tables[sid] = t
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(tables, f, ensure_ascii=False, indent=1)
    allstr = [s for t in tables.values() for s in t["strings"]]
    print(f"tables={len(tables)} strings={len(allstr)} unique={len(set(allstr))} "
          f"chars={sum(map(len, set(allstr)))}")
    for kind in ("ui", "scan", "world"):
        ks = [s for t in tables.values() if t["kind"] == kind for s in t["strings"]]
        print(f"  {kind}: tables={sum(t['kind'] == kind for t in tables.values())} strings={len(ks)} unique={len(set(ks))}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
