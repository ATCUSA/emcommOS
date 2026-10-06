# M1 manual hardware checks

Run on a real Debian 13 and a real Fedora machine after `sudo sh bootstrap.sh --repo-url URL`.
Record results (pass/fail, distro, **machine model** from
`cat /sys/class/dmi/id/product_name`, radio, notes) in the PR that closes M1. Run the USB
checks (2–3, 11) when you have physical access to a radio; the LAN checks (12–13) do not need it.

1. **Bootstrap**: `emcomm status` works; `id` shows `dialout` and `audio`; log out/in once.
2. **Detection**: plug in the radio; `emcomm station detect` lists its serial port and sound card.
3. **Station kit**: `sudo emcomm station add kita --radio <id>`; replug; `/dev/emcomm/cat-kita`
   exists and `aplay -l` shows card `EMCOMM_KITA`; `mmcli -L` does not list the radio.
4. **Hub**: `emcomm use <CALL> --station kita --yes`; `systemctl --user daemon-reload &&
   systemctl --user start emcomm-rigctld`; `rigctl -m 2 -r 127.0.0.1:4532 f` returns the
   radio's frequency; `rigctl -m 2 -r 127.0.0.1:4532 T 1; sleep 1; ... T 0` keys PTT
   (into a dummy load).
5. **WSJT-X**: Settings → Radio shows "Hamlib NET rigctl", 127.0.0.1:4532, PTT CAT;
   Test CAT and Test PTT succeed; Audio shows the EMCOMM card; FT8 decodes on a busy band.
6. **JS8Call**: same checks as WSJT-X. If the Audio dropdown lacks the EMCOMM card under Qt6,
   note the device name it shows (it may need a different SoundInName format).
7. **fldigi**: Configure → Rig → Hamlib shows "Use Hamlib", device 127.0.0.1:4532; frequency
   tracks the radio; PTT via Hamlib works. Select the audio device manually (M1 does not set
   fldigi audio) and note the PortAudio device name for M2.
8. **Direwolf**: `systemctl --user start emcomm-direwolf`; `journalctl --user -u
   emcomm-direwolf` shows the EMCOMM audio device opened and PTT via RIG.
9. **Pat**: `systemctl --user start emcomm-pat`; http://localhost:8080 loads; Settings shows
   rig "emcomm"; a telnet CMS connection works (enter Winlink password in Pat).
10. **Operator switch**: `emcomm operator add <CALL2> --grid <GRID2>`; `emcomm use <CALL2> --station kita`
    shows a diff of only call/grid lines; apply and confirm apps show the new call;
    previous files are in `~/.local/state/emcomm/backups/`.
11. **IC-7300MK2 (direct)**: `emcomm station detect` with the radio on USB-C. **Record the
    VID:PID, product string and interface numbers** of both ttyACM ports and the sound card
    in the PR so `radios/icom-ic7300mk2.yaml` can gain `usb_hints`.
    `sudo emcomm station add mk2 --radio icom-ic7300mk2 --cat ttyACM0 --audio cardN`;
    repeat checks 3–5 (rigctld uses hamlib model 3094).
12. **IC-7300MK2 over LAN via wfview (primary setup today)**: `sudo emcomm station add mk2
    --radio icom-ic7300mk2 --control wfview --virtual-audio`; `emcomm use <CALL> --station mk2`;
    restart PipeWire; in wfview connect to the radio's IP and set audio out/in to the
    emcomm virtual devices; record the exact device names WSJT-X and JS8Call list.
    For a USB-attached MK2 instead: `--cat ttyACM0 --audio cardN --control wfview`;
    start wfview, pick the radio's port, confirm waterfall; then
    `systemctl --user restart emcomm-rigctld` and repeat check 4 (frequency/PTT through
    127.0.0.1:4532 → wfview 4533) and check 5 (WSJT-X CAT/PTT while wfview shows the TX).
    Confirm `ss -ltn | grep 4533` and note that it listens on 0.0.0.0.
13. **IC-7300MK2 LAN (optional)**: connect wfview to the radio's Ethernet port (Network
    settings in wfview); record whether LAN control and audio work.
