#!/usr/bin/env python3
"""Check a Note9 rescue image against the DTB read from the actual phone.

This validates packaging and the deliberately limited bring-up configuration.
It cannot prove that the image will boot. It never connects to or writes a phone.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path


def fdt(blob):
    if len(blob) < 40:
        raise ValueError("truncated FDT header")
    magic, total, off_struct, off_strings = struct.unpack_from(">4I", blob)
    if magic != 0xD00DFEED or total > len(blob):
        raise ValueError("invalid FDT")
    strings = blob[off_strings:total]
    nodes, stack, pos = {}, [], off_struct
    while pos + 4 <= total:
        token = struct.unpack_from(">I", blob, pos)[0]
        pos += 4
        if token == 1:
            end = blob.index(0, pos)
            stack.append(blob[pos:end].decode())
            nodes["/" + "/".join(stack[1:])] = {}
            pos = (end + 4) & ~3
        elif token == 2:
            stack.pop()
        elif token == 3:
            size, offset = struct.unpack_from(">2I", blob, pos)
            pos += 8
            end = strings.index(0, offset)
            name = strings[offset:end].decode()
            if pos + size > total:
                raise ValueError("truncated FDT property")
            nodes["/" + "/".join(stack[1:])][name] = blob[pos:pos + size]
            pos = (pos + size + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            return nodes
        else:
            raise ValueError(f"invalid FDT token: {token}")
    raise ValueError("FDT has no end token")


def cells(value):
    return list(struct.unpack(">" + "I" * (len(value) // 4), value))


def memory(nodes):
    result = []
    for props in nodes.values():
        if props.get("device_type") == b"memory\0":
            values = cells(props["reg"])
            if len(values) % 3:
                raise ValueError("expected 2 address cells and 1 size cell")
            result.extend(tuple(values[i:i + 3]) for i in range(0, len(values), 3))
    return sorted(result)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stock-dtb", type=Path, required=True)
    ap.add_argument("--dtb", type=Path, required=True)
    ap.add_argument("--image", type=Path, required=True)
    ap.add_argument("--reference", type=Path, required=True)
    ap.add_argument("--boot-size", type=int, default=57671680)
    ap.add_argument("--stage", choices=("usb", "storage", "touch", "system", "gpu", "radios"), default="usb")
    ap.add_argument("--persistent", action="store_true")
    ap.add_argument("--writable-state", action="store_true")
    args = ap.parse_args()
    require(not args.persistent or args.stage in ("system", "gpu", "radios"), "persistent mode requires userspace stage")
    stock, new = fdt(args.stock_dtb.read_bytes()), fdt(args.dtb.read_bytes())
    require(b"Crown" in stock["/"].get("model", b""), "stock DTB is not a Crown board")
    require(new["/"]["compatible"].split(b"\0")[0] == b"samsung,crownlte", "wrong target compatible")
    require(memory(stock) == memory(new), "RAM banks differ from this phone")
    require(sum(row[2] for row in memory(new)) > 5 * 1024**3, "expected the 6 GB model")
    for prop in ("model_info-chip", "model_info-hw_rev", "model_info-hw_rev_end"):
        require(stock["/"][prop] == new["/"][prop], f"board selector mismatch: {prop}")
    bootargs = stock["/chosen"]["bootargs"]
    require(b"s3cfb.bootloaderfb=0xcc000000" in bootargs, "different boot framebuffer")
    touch = stock["/hsi2c@104B0000/touchscreen@48"]
    require(b"y771_crown" in touch["sec,firmware_name"], "unexpected touchscreen")
    reserved = []
    for path, props in new.items():
        if path.startswith("/reserved-memory/") and "reg" in props:
            hi, lo, size = cells(props["reg"])
            start = (hi << 32) | lo
            reserved.append((start, start + size))
    reserved.sort()
    merged = []
    for start, end in reserved:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    for path, props in stock.items():
        if path.startswith("/reserved-memory/") and "reg" in props:
            hi, lo, size = cells(props["reg"])
            start = (hi << 32) | lo
            require(any(a <= start and start + size <= b for a, b in merged),
                    f"stock firmware reservation not protected: {path}")
    risky = (b"samsung,exynos9810-ufs", b"samsung,s6sy761", b"samsung,s6sy771", b"arm,mali-bifrost",
             b"samsung,exynos9810-decon", b"samsung,exynos9810-pcie",
             b"maxim,max77705", b"maxim,max77705-charger", b"maxim,max77705-battery")
    ufs_nodes = [v for v in new.values() if b"samsung,exynos9810-ufs" in v.get("compatible", b"").split(b"\0")]
    require(len(ufs_nodes) == 1, "expected exactly one UFS controller")
    touch_nodes = [v for v in new.values() if b"samsung,s6sy771" in v.get("compatible", b"").split(b"\0")]
    require(len(touch_nodes) == 1, "expected exactly one Crown Y771 touchscreen")
    gpu_nodes = [(p, v) for p, v in new.items() if b"arm,mali-bifrost" in v.get("compatible", b"").split(b"\0")]
    require(len(gpu_nodes) == 1, "expected exactly one Mali GPU")
    for compatible in (b"samsung,exynos9810-g3d-pd", b"samsung,exynos9810-g3d-clock"):
        suppliers = [v for v in new.values() if compatible in v.get("compatible", b"").split(b"\0")]
        require(len(suppliers) == 1, "missing or duplicate G3D supplier")
        require(suppliers[0].get("status", b"okay\0") == (b"okay\0" if args.stage in ("gpu", "radios") else b"disabled\0"),
                "G3D supplier state does not match stage")
    if args.stage in ("gpu", "radios"):
        gpu_path, gpu_props = gpu_nodes[0]
        require(cells(stock["/mali@17500000"]["reg"]) == [0, 0x17500000, 0x5000], "unexpected stock GPU registers")
        require(cells(gpu_props["reg"]) == [0x17500000, 0x5000], "GPU register range differs")
        opps = [v for p, v in new.items() if p.startswith(gpu_path + "/") and "opp-hz" in v]
        require(len(opps) == 1 and struct.unpack(">Q", opps[0]["opp-hz"])[0] == 260000000,
                "initial GPU test must stay at 260 MHz")
        rails = [v for v in stock.values() if v.get("regulator-name") == b"vdd_g3d\0"]
        require(len(rails) == 1, "missing stock G3D voltage limits")
        require(cells(rails[0]["regulator-min-microvolt"])[0] <= cells(opps[0]["opp-microvolt"])[0]
                <= cells(rails[0]["regulator-max-microvolt"])[0], "GPU voltage exceeds stock regulator limits")
    require(new["/regulator-ufs-vcc"]["status"] == (b"disabled\0" if args.stage == "usb" else b"okay\0"),
            "UFS supply state does not match test stage")
    if args.stage == "radios":
        battery = [v for v in new.values() if v.get("compatible") == b"simple-battery\0"]
        require(len(battery) == 1, "expected one Crown battery description")
        require(cells(battery[0]["charge-full-design-microamp-hours"]) == [4000000], "wrong Crown capacity")
        require(cells(battery[0]["constant-charge-current-max-microamp"]) == [1000000], "expected requested 1 A limit")
        require(cells(battery[0]["constant-charge-voltage-max-microvolt"]) == [4350000], "wrong Crown float voltage")
        require(cells(stock["/battery"]["battery,chg_float_voltage"]) == [4350], "stock float voltage differs")
        pcie = [v for v in new.values() if v.get("compatible") == b"samsung,exynos9810-pcie\0"]
        require(len(pcie) == 1, "expected one Wi-Fi PCIe host")
        stock_regs = cells(stock["/pcie0@116A0000"]["reg"])
        stock_ranges = [(stock_regs[i + 1], stock_regs[i + 2]) for i in range(0, len(stock_regs), 3)]
        regs = cells(pcie[0]["reg"])
        require(all(tuple(regs[i:i + 2]) in stock_ranges for i in range(0, len(regs), 2)), "PCIe register range differs from Crown")
        require(cells(pcie[0]["interrupts"]) == [0, 253, 4], "wrong Wi-Fi PCIe interrupt")
    for path, props in new.items():
        compatibles = props.get("compatible", b"").split(b"\0")
        if b"samsung,exynos9810-ufs" in compatibles and args.stage != "usb":
            require(props.get("status") == b"okay\0", "storage test requires UFS enabled")
            continue
        if b"samsung,s6sy771" in compatibles and args.stage in ("touch", "system", "gpu", "radios"):
            require(props.get("status", b"okay\0") == b"okay\0", "touch stage requires the Y771 node enabled")
            continue
        if b"arm,mali-bifrost" in compatibles and args.stage in ("gpu", "radios"):
            require(props.get("status") == b"okay\0", "GPU probe requires Panfrost node enabled")
            continue
        if args.stage == "radios" and any(c in compatibles for c in
                (b"samsung,exynos9810-pcie", b"maxim,max77705", b"maxim,max77705-charger", b"maxim,max77705-battery")):
            require(props.get("status", b"okay\0") == b"okay\0", f"radio/power node disabled: {path}")
            continue
        if any(c in risky for c in compatibles):
            require(props.get("status") == b"disabled\0", f"unvalidated hardware enabled: {path}")
    require(cells(new["/clock-gates"]["s9p,set-registers"])[2:4] == [0x1406080c, 0x12345674],
            "kernel does not arm recovery fallback")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "third_party/s9plus/scripts/build"))
    from boot_parts import parts
    from mkboot import image_id
    image, reference = args.image.read_bytes(), args.reference.read_bytes()
    require(len(image) <= args.boot_size, "image exceeds BOOT partition")
    packed, ref = parts(image), parts(reference)
    require(packed["dt"] == ref["dt"], "Samsung DTBH differs from the phone's accepted recovery")
    require(image[576:608] == image_id(packed["kernel"], packed["ramdisk"], packed["second"], packed["dt"]),
            "boot image SHA1 ID mismatch")
    require(b"SEANDROIDENFORCE" in image[-2048:], "missing Samsung trailer")
    require(args.dtb.read_bytes() in packed["kernel"], "target DTB is not embedded in uniLoader")
    rescue = 0 if args.stage in ("system", "gpu", "radios") else 1
    deadline = 0 if args.persistent else 120
    require(f"zboot.rescue={rescue} zboot.test=1 zboot.deadman={deadline} ".encode() in packed["kernel"],
            "missing expected test deadline command line")
    require((b"zboot.persistent=1" in packed["kernel"]) == args.persistent,
            "persistent image requires explicit persistent verification")
    state_arg = b"zboot.statefile=/unencrypted/ztos/crownlte-state.img"
    require((state_arg in packed["kernel"]) == args.writable_state,
            "writable state requires explicit verification")
    require(not args.writable_state or args.stage == "radios", "writable state requires radios stage")
    if args.stage != "usb":
        require(f"zboot.stage={args.stage}".encode() in packed["kernel"], "test command line does not match stage")
    for other in ("storage", "touch", "system", "gpu", "radios"):
        if other != args.stage:
            require(f"zboot.stage={other}".encode() not in packed["kernel"], "image requires its explicit test stage")
    if args.stage in ("system", "gpu", "radios"):
        require(b"zboot.rootfile=/unencrypted/ztos/crownlte-root.img" in packed["kernel"], "wrong root image path")
    print(json.dumps({"device": "crownlte", "model": "SM-N960F", "stage": args.stage,
                      "boot_mode": "persistent-test" if args.persistent else "bounded-test",
                      "ram_banks_match": True, "stock_reservations_covered": True, "samsung_dtbh_matches": True,
                      "boot_image_id_valid": True, "bytes": len(image),
                      "sha256": hashlib.sha256(image).hexdigest()}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError, OSError, struct.error) as error:
        sys.exit(f"crownlte verification failed: {error}")
