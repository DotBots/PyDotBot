#!/usr/bin/env python3
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .boards import is_multicore_family

# Timings
POLL_INTERVAL = 1.0
TIMEOUT_JLINK_SEC = 120
TIMEOUT_BUILD_SEC = 900
TIMEOUT_MAINTENANCE_SEC = 300
# A recover erases a whole core and can take minutes on a slow J-Link.
TIMEOUT_RECOVER_SEC = 600

DEFAULT_SWD_SPEED_KHZ = 4000


def run(cmd, timeout=None, cwd=None):
    print(f"[CMD] {' '.join(cmd)}")
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        cwd=cwd,
    )
    print(proc.stdout)
    return proc.returncode, proc.stdout


def run_capture(cmd):
    proc = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    if proc.returncode != 0:
        raise_if_protected(proc.returncode, proc.stdout, _family_of(cmd))
        raise RuntimeError(proc.stdout.strip() or f"Command failed: {' '.join(cmd)}")
    return proc.stdout


# ---------- Access port protection (APPROTECT) ----------
#: UICR value that leaves an access port open ("Unprotected"). Any other value,
#: including the erased 0xFFFFFFFF, protects it (nRF5340 PS v1.6, 5.4.3.1).
APPROTECT_UNPROTECTED = 0x50FA50FA

#: The nRF5340 UICR words that must hold APPROTECT_UNPROTECTED for the chip to
#: stay debuggable across a power cycle, as (coprocessor, address).
NRF53_UICR_APPROTECT_WORDS = (
    ("CP_APPLICATION", 0x00FF8000),  # UICR.APPROTECT
    ("CP_APPLICATION", 0x00FF801C),  # UICR.SECUREAPPROTECT
    ("CP_NETWORK", 0x01FF8000),  # network core UICR.APPROTECT
)

#: nrfjprog's exit code for NOT_AVAILABLE_BECAUSE_PROTECTION.
NRFJPROG_PROTECTED_RC = 16


class AccessPortProtected(RuntimeError):
    """nrfjprog was refused because the chip's access port is protected."""

    def __init__(self, family: str = "NRF53"):
        super().__init__(
            "The chip's access port is protected (APPROTECT), so nrfjprog "
            "cannot program or read it. A factory-fresh nRF5340 is in this "
            "state. Unlocking it ERASES the whole chip:\n"
            "  - DotBot v3: dotbot device flash swarmit-sandbox --probe 77\n"
            "  - gateway DK: dotbot device flash mari-gateway --probe 10\n"
            "Both recover the chip, flash it and leave it unlocked. For any "
            f"other firmware: nrfjprog -f {family} --recover, then flash again."
        )
        self.family = family


def is_protected(rc: int, out: str) -> bool:
    """True if an nrfjprog result means the access port refused the debugger."""
    if rc == 0:
        return False
    text = out.lower()
    return (
        rc == NRFJPROG_PROTECTED_RC
        or "readback protection" in text
        or "access protection" in text
        or "approtect" in text
    )


def raise_if_protected(rc: int, out: str, family: str = "NRF53") -> None:
    if is_protected(rc, out):
        raise AccessPortProtected(family)


def _family_of(cmd) -> str:
    try:
        return cmd[cmd.index("-f") + 1]
    except (ValueError, IndexError):
        return "NRF53"


def nrfjprog_disable_approtect(nrfjprog, snr=None):
    """Write APPROTECT_UNPROTECTED to every nRF5340 UICR protection word.

    Without it an erased chip re-protects itself on the next power cycle, since
    erased UICR reads as protected. The firmware copies these words into
    CTRLAP.*.DISABLE at boot (the MDK's nrf53_handle_approtect). The words must
    be erased when this runs: UICR bits only program from 1 to 0.
    """
    for core, addr in NRF53_UICR_APPROTECT_WORDS:
        args = [nrfjprog, "-f", "NRF53"]
        if snr:
            args += ["-s", str(snr)]
        args += ["--coprocessor", core]
        args += ["--memwr", f"0x{addr:08X}", "--val", f"0x{APPROTECT_UNPROTECTED:08X}"]
        rc, out = run(args, timeout=60)
        raise_if_protected(rc, out)
        if rc != 0 or "ERROR" in out.upper():
            raise RuntimeError(
                f"Writing UICR 0x{addr:08X} ({core}) failed; see log above."
            )


def approtect_disabled_in_uicr(snr: str | None = None) -> bool:
    """True if every nRF5340 UICR protection word holds APPROTECT_UNPROTECTED.

    False means the chip will be protected again after its next power cycle.
    Reading the network core's word resets that core, like read_net_id.
    """
    nrfjprog = which_tool("nrfjprog.exe", candidates=_NRFJPROG_CANDIDATES)
    for core, addr in NRF53_UICR_APPROTECT_WORDS:
        args = [nrfjprog, "-f", "NRF53", "--coprocessor", core]
        args += ["--memrd", f"0x{addr:08X}", "--n", "4"]
        if snr:
            args += ["-s", str(snr)]
        words = _parse_memrd_words(run_capture(args))
        if not words or int(words[0], 16) != APPROTECT_UNPROTECTED:
            return False
    return True


def which_tool(exe_name, user_supplied=None, candidates=None):
    if user_supplied:
        return user_supplied
    p = shutil.which(exe_name)
    if p:
        return p
    for c in candidates or []:
        if Path(c).exists():
            return c
    return exe_name


_NRFJPROG_CANDIDATES = (
    "/usr/local/bin/nrfjprog",
    "/usr/bin/nrfjprog",
)


def nrfjprog_available() -> bool:
    """True if the `nrfjprog` Nordic command-line tool can be located.

    Checks PATH (both `nrfjprog` and the Windows `nrfjprog.exe`) plus the
    well-known install locations. Lets the device commands fail fast with
    a friendly install hint instead of a late, cryptic subprocess error.
    """
    if shutil.which("nrfjprog") or shutil.which("nrfjprog.exe"):
        return True
    return any(Path(c).exists() for c in _NRFJPROG_CANDIDATES)


# ---------- JLink / DAPLink (APM32F103) ----------
def make_jlink_script(device, speed_khz, hex_path):
    lines = []
    lines.append(f"device {device}")
    lines.append("si SWD")
    if speed_khz:
        lines.append(f"speed {speed_khz}")
    lines.append("connect")
    lines.append("h")
    lines.append("r")
    lines.append("erase")
    lines.append(f"loadfile {hex_path}")
    lines.append("verify")
    lines.append("r")
    lines.append("g")
    lines.append("exit")
    return "\n".join(lines)


def jlink_flash_hex(jlink_exe, device, image_hex, timeout=TIMEOUT_JLINK_SEC):
    speed_khz = DEFAULT_SWD_SPEED_KHZ
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".jlink") as tf:
        tf.write(make_jlink_script(device, speed_khz, str(image_hex)))
        script_path = tf.name
    try:
        rc, out = run([jlink_exe, "-CommanderScript", script_path], timeout=timeout)
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass
    if rc != 0 or "ERROR" in out.upper() or "FAILED" in out.upper():
        raise RuntimeError("J-Link flash failed; see log above.")


def pyocd_flash_hex(jlink_bin, device, pack_path: str, probe_uid: str | None = None):
    erase_args = [
        "pyocd",
        "erase",
        "--chip",
        "--pack",
        pack_path,
        "-t",
        str(device),
    ]
    if probe_uid:
        erase_args += ["--uid", probe_uid]
    rc, out = run(erase_args, timeout=60)
    args = ["pyocd", "flash", str(jlink_bin)]
    args += ["--pack", pack_path]
    args += ["-t", str(device)]
    if probe_uid:
        args += ["--uid", probe_uid]
    rc, out = run(args, timeout=120)


def do_daplink(
    bl_hex: Path,
    apm_device: str,
    jlinktool: str | None,
    pack_path: str,
    probe_uid: str | None = None,
):
    """Flash STM32 bootloader (DAPLink) using external J-Link."""
    jlink_tool = which_tool(
        "JLink.exe",
        jlinktool,
        candidates=[
            # r"C:\Program Files\SEGGER\JLink_V818\JLink.exe",
            "/usr/local/bin/JLinkExe",
            "/usr/bin/JLinkExe",
        ],
    )
    if not bl_hex.exists():
        raise FileNotFoundError(f"Bootloader image not found: {bl_hex}")

    print("== Flashing STM32 bootloader (DAPLink) to APM32F103CB ==")
    jlink_flash_hex(jlink_tool, apm_device, bl_hex)
    print("[OK] DAPLink bootloader programmed.")


def do_daplink_if(
    if_hex: Path, apm_device: str, pack_path: str, probe_uid: str | None = None
):
    """Flash DAPLink interface firmware over SWD using pyOCD."""
    if not if_hex.exists():
        raise FileNotFoundError(f"DAPLink interface image not found: {if_hex}")

    print("== Flashing DAPLink interface image via pyOCD ==")
    pyocd_flash_hex(if_hex, apm_device, pack_path, probe_uid=probe_uid)
    print("[OK] DAPLink interface programmed.")


def do_jlink(
    jlink_bin: Path,
    bl_hex: Path,
    apm_device: str,
    jlinktool: str | None,
    pack_path: str,
    probe_uid: str | None = None,
):
    """Flash STM32 bootloader, then J-Link OB image (overwrites BL)."""
    if not jlink_bin.exists():
        raise FileNotFoundError(f"J-Link OB image not found: {jlink_bin}")

    do_daplink(
        bl_hex=bl_hex,
        apm_device=apm_device,
        jlinktool=jlinktool,
        pack_path=pack_path,
    )

    print("[INFO] Waiting 5 seconds for STM32 bootloader to enumerate...")
    time.sleep(5)

    print("== Flashing J-Link OB image via pyOCD ==")
    pyocd_flash_hex(jlink_bin, apm_device, pack_path, probe_uid=probe_uid)
    print("[OK] J-Link OB programmed.")


# ---------- Flash nRF5340 with nrfjprog ----------
def pick_last_jlink_snr(nrfjprog_opt=None):
    nrfjprog = which_tool(
        "nrfjprog.exe",
        nrfjprog_opt,
        candidates=[
            # r"C:\Program Files\Nordic Semiconductor\nrf-command-line-tools\bin\nrfjprog.exe"
            "/usr/local/bin/nrfjprog",
            "/usr/bin/nrfjprog",
        ],
    )

    rc2, out2 = run([nrfjprog, "--ids"], timeout=10)
    ids = (
        [line.strip() for line in out2.splitlines() if line.strip().isdigit()]
        if rc2 == 0
        else []
    )
    print(f"[DEBUG] Found J-Link IDs: {ids}")
    if ids:
        return ids[-1]
    raise RuntimeError(
        "Unable to auto-select J-Link; pass --probe with the board's "
        "J-Link serial-number prefix (e.g. --probe 77)."
    )


def pick_matching_jlink_snr(sn_starting_digits: str, nrfjprog_opt: str | None = None):
    nrfjprog = which_tool(
        "nrfjprog.exe",
        nrfjprog_opt,
        candidates=[
            # r"C:\Program Files\Nordic Semiconductor\nrf-command-line-tools\bin\nrfjprog.exe"
            "/usr/local/bin/nrfjprog",
            "/usr/bin/nrfjprog",
        ],
    )
    rc2, out2 = run([nrfjprog, "--ids"], timeout=10)
    ids = (
        [
            line.strip()
            for line in out2.splitlines()
            if line.strip().isdigit() and line.strip().startswith(sn_starting_digits)
        ]
        if rc2 == 0
        else []
    )
    print(f"[DEBUG] Found J-Link IDs: {ids}")
    if not ids:
        raise RuntimeError(
            f"No J-Link found with serial number starting with {sn_starting_digits}"
        )
    return ids[0]


def nrfjprog_recover(nrfjprog, snr=None, timeout=TIMEOUT_RECOVER_SEC):
    """Unprotect and erase both nRF5340 cores (a whole-chip erase)."""
    args = [nrfjprog, "-f", "NRF53"]
    if snr:
        args += ["-s", str(snr)]
    print(f"[INFO] Recovering both cores of nRF5340 (SNR={snr})...")
    steps = (
        ["--recover", "--coprocessor", "CP_APPLICATION"],
        ["--recover", "--coprocessor", "CP_NETWORK"],
        ["-e"],
    )
    for step in steps:
        if step == ["-e"]:
            print(f"[INFO] Erasing both cores of nRF5340 (SNR={snr})...")
        try:
            rc, out = run(args + step, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"nrfjprog {' '.join(step)} did not finish within {timeout} s. "
                "Check the cable and the board's power, then run the command "
                "again."
            ) from exc
        if rc != 0 or "ERROR" in out.upper():
            raise RuntimeError(
                f"nrfjprog {' '.join(step)} failed; see log above. If it keeps "
                "failing, power-cycle the board and try again."
            )


def nrfjprog_program(
    nrfjprog,
    hex_path,
    network=False,
    family="NRF53",
    verify=True,
    reset=True,
    chiperase=True,
    sectorerase=False,
    snr=None,
):
    if chiperase and sectorerase:
        raise ValueError("Use only one of chiperase or sectorerase.")
    args = [nrfjprog, "-f", family]
    if snr:
        args += ["-s", str(snr)]
    # --coprocessor only applies to multi-core families (the nRF5340); a
    # single-core family (nRF52) has no coprocessor and rejects the flag.
    if is_multicore_family(family):
        args += ["--coprocessor", "CP_NETWORK" if network else "CP_APPLICATION"]
    args += ["--program", str(hex_path)]
    if verify:
        args += ["--verify"]
    if chiperase:
        args += ["--chiperase"]
    elif sectorerase:
        args += ["--sectorerase"]
    if reset:
        args += ["--reset"]
    rc, out = run(args, timeout=120)
    raise_if_protected(rc, out, family)
    if rc != 0 or "ERROR" in out.upper() or "failed" in out.lower():
        raise RuntimeError("nrfjprog programming failed; see log above.")


def _parse_memrd_words(output: str) -> list[str]:
    line = output.strip().splitlines()[0] if output.strip() else ""
    if ":" not in line:
        raise RuntimeError(f"Unexpected memrd output: {output.strip()}")
    _, rest = line.split(":", 1)
    words = [w for w in rest.strip().split() if not w.startswith(("0x", "0X"))]
    return words


def read_device_id(snr: str | None = None) -> str:
    nrfjprog = which_tool(
        "nrfjprog.exe",
        candidates=[
            # r"C:\Program Files\Nordic Semiconductor\nrf-command-line-tools\bin\nrfjprog.exe"
            "/usr/local/bin/nrfjprog",
            "/usr/bin/nrfjprog",
        ],
    )
    # Read FICR.INFO.DEVICEID from the APPLICATION core. The same value is
    # mirrored in the network core's FICR, but attaching the debugger to that
    # coprocessor resets it, which kills the radio on a running bot; the
    # application core reads back with no side effect.
    args = [nrfjprog, "-f", "NRF53"]
    args += ["--memrd", "0x00FF0204"]
    args += ["--n", "8"]
    if snr:
        args += ["-s", str(snr)]
    out = run_capture(args)
    words = _parse_memrd_words(out)
    if len(words) < 2:
        raise RuntimeError(f"Unexpected device ID output: {out.strip()}")
    return f"{words[1]}{words[0]}"


#: Reading the swarmit config page means attaching to the network core, which
#: resets it. A bot that was running loses its radio and looks dead until the
#: whole device is reset, so callers must say they accept that.
NET_CORE_READ_WARNING = (
    "Reading the network id attaches the debugger to the network core, which "
    "RESETS it. If this DotBot is running an experiment it will drop off the "
    "network and stay off until the device is reset."
)


def read_net_id(snr: str | None = None) -> str:
    nrfjprog = which_tool(
        "nrfjprog.exe",
        candidates=[
            # r"C:\Program Files\Nordic Semiconductor\nrf-command-line-tools\bin\nrfjprog.exe"
            "/usr/local/bin/nrfjprog",
            "/usr/bin/nrfjprog",
        ],
    )
    args = [nrfjprog, "-f", "NRF53"]
    args += ["--coprocessor", "CP_NETWORK"]
    # Read both has_net_id (offset 4) and net_id (offset 8) from the swarmit
    # config page; layout matches swarmit_config_t (see create_config_hex
    # in cli.py and DotBots/swarmit network_core/Source/main.c).
    args += ["--memrd", "0x0103F804"]
    args += ["--n", "8"]
    if snr:
        args += ["-s", str(snr)]
    out = run_capture(args)
    words = _parse_memrd_words(out)
    if len(words) < 2:
        raise RuntimeError(f"Unexpected net ID output: {out.strip()}")
    has_net_id, net_id = words[0], words[1]
    if int(has_net_id, 16) != 1:
        return "unprovisioned"
    return f"{net_id[-4:]}"


def flash_nrf_both_cores(
    app_hex: Path,
    net_hex: Path,
    nrfjprog_opt: str | None,
    snr_opt: str | None,
    reset: bool = True,
):
    """Flash nRF5340 application and network cores with full recover + chiperase.

    ``reset=False`` leaves both cores halted so a caller that still has pages to
    write (the config page, a default app) can program everything first and
    reset once at the end. Resetting between writes would boot the cores against
    a half-provisioned device.
    """
    if not app_hex.exists():
        raise FileNotFoundError(f"App hex not found: {app_hex}")
    if not net_hex.exists():
        raise FileNotFoundError(f"Net hex not found: {net_hex}")

    nrfjprog = which_tool(
        "nrfjprog.exe",
        nrfjprog_opt,
        candidates=[
            # r"C:\Program Files\Nordic Semiconductor\nrf-command-line-tools\bin\nrfjprog.exe"
            "/usr/local/bin/nrfjprog",
            "/usr/bin/nrfjprog",
        ],
    )

    snr = snr_opt or pick_last_jlink_snr(nrfjprog)
    print(f"[INFO] Using J-Link with serial number: {snr}")

    nrfjprog_recover(nrfjprog, snr=snr)

    # The network core is programmed first so the application core, which waits
    # on it during bring-up, never boots against a blank peer. Neither program
    # step resets: the two cores hand-shake over shared memory at startup, so
    # they have to start together, which the CTRL-AP reset below does.
    print("== Flashing nRF5340 network core with nrfjprog ==")
    nrfjprog_program(
        nrfjprog,
        net_hex,
        network=True,
        verify=True,
        reset=False,
        chiperase=True,
        snr=snr,
    )
    print("[OK] Network core programmed.")

    print("== Flashing nRF5340 application core with nrfjprog ==")
    nrfjprog_program(
        nrfjprog,
        app_hex,
        network=False,
        verify=True,
        reset=False,
        chiperase=True,
        snr=snr,
    )
    print("[OK] Application core programmed.")

    # Leaves the debug port open for good; a locked-down image skips this.
    nrfjprog_disable_approtect(nrfjprog, snr=snr)
    print("[OK] APPROTECT disabled in UICR on both cores.")

    if reset:
        nrfjprog_debugreset(nrfjprog, snr=snr)
        print("[OK] Device reset (CTRL-AP).")


def flash_nrf_one_core(
    app_hex: Path | None = None,
    net_hex: Path | None = None,
    family: str = "NRF53",
    nrfjprog_opt: str | None = None,
    snr_opt: str | None = None,
    reset: bool = True,
):
    """Flash only one core; no recover and no chiperase.

    `family` is the nrfjprog `-f` value ("NRF53" / "NRF52"). On nRF52 there is
    no network core, so `net_hex` and the per-core reset are nRF5340-only.
    """
    if app_hex is None and net_hex is None:
        raise FileNotFoundError("Provide app_hex or net_hex.")
    if app_hex is not None and net_hex is not None:
        raise FileNotFoundError("Provide only one of app_hex or net_hex.")
    if app_hex is not None and not app_hex.exists():
        raise FileNotFoundError(f"App hex not found: {app_hex}")
    if net_hex is not None and not net_hex.exists():
        raise FileNotFoundError(f"Net hex not found: {net_hex}")

    nrfjprog = which_tool(
        "nrfjprog.exe",
        nrfjprog_opt,
        candidates=[
            # r"C:\Program Files\Nordic Semiconductor\nrf-command-line-tools\bin\nrfjprog.exe"
            "/usr/local/bin/nrfjprog",
            "/usr/bin/nrfjprog",
        ],
    )

    snr = snr_opt or pick_last_jlink_snr(nrfjprog)
    print(f"[INFO] Using J-Link with serial number: {snr}")

    if app_hex is not None:
        print(f"== Flashing {family} application core with nrfjprog ==")
        nrfjprog_program(
            nrfjprog,
            app_hex,
            network=False,
            family=family,
            verify=True,
            reset=True,
            chiperase=False,
            sectorerase=True,
            snr=snr,
        )
        print("[OK] Application core programmed.")
    else:
        print(f"== Flashing {family} network core with nrfjprog ==")
        nrfjprog_program(
            nrfjprog,
            net_hex,
            network=True,
            family=family,
            verify=True,
            reset=True,
            chiperase=False,
            sectorerase=True,
            snr=snr,
        )
        print("[OK] Network core programmed.")
    if not reset:
        return
    time.sleep(0.5)
    if is_multicore_family(family):
        # One CTRL-AP reset for the whole device rather than a SysResetReq per
        # core: the cores hand-shake over shared memory during bring-up, so
        # restarting them one at a time strands whichever starts first, and the
        # SwarmIT bootloader refuses SysResetReq outright (see
        # nrfjprog_debugreset).
        nrfjprog_debugreset(nrfjprog, snr=snr, family=family)
    else:
        # single-core family: one reset, no --coprocessor
        nrfjprog_reset_core(nrfjprog, snr=snr, core=None, family=family)


def nrfjprog_debugreset(nrfjprog, snr=None, family="NRF53"):
    """Reset the whole device through CTRL-AP.

    `--reset` issues a SysResetReq, which firmware can refuse: the SwarmIT
    bootloader sets `SCB_AIRCR.SYSRESETREQS` to keep non-secure code from
    resetting the SoC, and the request is then dropped. A device flashed that
    way keeps running its pre-flash state until someone presses the button.
    CTRL-AP resets from the debug domain instead, so firmware cannot veto it.
    """
    args = [nrfjprog, "-f", family]
    if snr:
        args += ["-s", str(snr)]
    args += ["--debugreset"]
    rc, out = run(args, timeout=120)
    raise_if_protected(rc, out, family)
    if rc != 0 or "ERROR" in out.upper() or "failed" in out.lower():
        raise RuntimeError("nrfjprog debug reset failed; see log above.")


def reset_device(snr=None, family="NRF53", nrfjprog_opt=None, settle: float = 2.0):
    """CTRL-AP reset of the whole device, for callers that staged writes.

    ``settle`` waits before resetting: a reset issued immediately after the last
    programming step has been observed to leave the device down, while the same
    reset a couple of seconds later brings it up.
    """
    nrfjprog = which_tool(
        "nrfjprog.exe",
        nrfjprog_opt,
        candidates=["/usr/local/bin/nrfjprog", "/usr/bin/nrfjprog"],
    )
    if settle:
        time.sleep(settle)
    nrfjprog_debugreset(nrfjprog, snr=snr, family=family)
    # A CTRL-AP reset can leave the core halted, which looks exactly like a dead
    # board: programmed, reset, and never running. Start it explicitly. Best
    # effort - if the core is already running this is a no-op that some tool
    # versions report as an error.
    args = [nrfjprog, "-f", family]
    if snr:
        args += ["-s", str(snr)]
    run(args + ["--run"], timeout=60)


def nrfjprog_reset_core(nrfjprog, snr=None, core="CP_APPLICATION", family="NRF53"):
    args = [nrfjprog, "-f", family]
    if snr:
        args += ["-s", str(snr)]
    args += ["--reset"]
    # --coprocessor is multi-core-only; a single-core family resets directly.
    if is_multicore_family(family) and core:
        args += ["--coprocessor", core]
    rc, out = run(args, timeout=120)
    raise_if_protected(rc, out, family)
    if rc != 0 or "ERROR" in out.upper() or "failed" in out.lower():
        raise RuntimeError("nrfjprog reset failed; see log above.")
