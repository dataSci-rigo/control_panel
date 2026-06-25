# Control Panel

Flask control panel for the a-bot VM. Runs on port 9000 (Tailscale-only).

## Deploy to VM

```bash
# On the VM — clone once
git clone git@github.com:dataSci-rigo/control_panel.git ~/apps/panel

# After any update — pull and restart
cd ~/apps/panel
git pull
sudo systemctl restart app-panel
```

## Check logs

```bash
sudo journalctl -u app-panel -n 60 --no-pager
```
