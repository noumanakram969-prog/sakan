# Deploying to the AlmaLinux VPS

Meta will only send webhooks to a public HTTPS endpoint, so this has to be a real
server with a real certificate. About 30 minutes the first time.

Replace `bot.example.ae` throughout with the subdomain you point at the VPS.

## 1. DNS first

Point an A record at the VPS and wait for it to resolve. Certbot cannot issue a
certificate before this is true, and everything downstream depends on it.

```bash
dig +short bot.example.ae
```

## 2. User and code

```bash
sudo useradd -r -m -d /opt/mistri -s /sbin/nologin mistri
sudo dnf install -y python3.11 git nginx
sudo -u mistri git clone <repo> /opt/mistri
cd /opt/mistri
sudo -u mistri python3.11 -m venv .venv
sudo -u mistri .venv/bin/pip install -r requirements.txt
```

## 3. Configuration

```bash
sudo -u mistri cp .env.example .env
sudo -u mistri vi .env
sudo chmod 600 .env
```

Fill in, at minimum:

| Setting | Where it comes from |
|---|---|
| `WA_PROVIDER` | `meta` for the test number, `d360` for Care's real number |
| `META_*` / `D360_API_KEY` | the app dashboard or the 360dialog hub |
| `META_VERIFY_TOKEN` | invent one; it goes in Meta's webhook form too |
| `META_APP_SECRET` | required, or every webhook is rejected as unsigned |
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `ADMIN_PASSWORD` | anything but the default - the admin page returns 503 until you change it |
| `WEBHOOK_TOKEN` | required with `WA_PROVIDER=d360`; a long random string |

Then check the garage's own files are actually usable:

```bash
sudo -u mistri .venv/bin/python -m app.cli check --garage care
```

It lists every price still unfilled. Each one is a question the bot will hand to
the owner instead of answering, so know the number before he finds it.

## 4. nginx and the certificate

```bash
sudo cp deploy/nginx.conf /etc/nginx/conf.d/mistri.conf
sudo vi /etc/nginx/conf.d/mistri.conf     # set server_name, restrict /admin
sudo nginx -t && sudo systemctl reload nginx
sudo dnf install -y certbot python3-certbot-nginx
sudo certbot --nginx -d bot.example.ae
```

Certbot rewrites the file with the real certificate paths. Renewal is automatic;
check it with `sudo certbot renew --dry-run`.

## 5. The service

```bash
sudo cp deploy/mistri.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mistri
curl -s https://bot.example.ae/health
```

Expect `{"status":"ok","provider":"meta"}`.

**One worker, deliberately.** The scheduler runs inside the process. A second
worker would send every reminder twice, and a customer who gets two identical
reminders stops trusting the whole thing.

## 6. Point Meta at it

In the app dashboard (or the 360dialog hub), set:

- Callback URL: `https://bot.example.ae/webhook`
  (on 360dialog: `https://bot.example.ae/webhook?token=<WEBHOOK_TOKEN>` - it does
  not sign its requests, so that token is the only thing standing between the
  garage's number and anyone who guesses the URL)
- Verify token: whatever `META_VERIFY_TOKEN` says
- Subscribe to the **messages** field

Meta calls `GET /webhook` immediately to verify. If it fails, the token does not
match or nginx is not forwarding — `journalctl -u mistri -f` shows which.

## 7. Prove it end to end

```bash
journalctl -u mistri -f
```

Message the test number from your own phone and watch a reply come back. Then:

- Open `https://bot.example.ae/admin/` and find the conversation.
- Reply from the business phone and confirm the bot goes quiet in that chat.
- Send `/status` from the owner's number and confirm the numbers come back.

## Day to day

```bash
# what happened this month
sudo -u mistri .venv/bin/python -m app.cli report --garage care --from 2026-09-01 --to 2026-09-30

# every reply the guard stopped, which is the log line worth watching
journalctl -u mistri | grep BLOCKED

# deploy a change
cd /opt/mistri && sudo -u mistri git pull
sudo -u mistri .venv/bin/pip install -r requirements.txt
sudo systemctl restart mistri
```

## Backups

Everything is in one SQLite file. Back it up before anything else — it is the
pilot report, and the pilot report is what sells garage number two.

```bash
sudo cp deploy/backup.sh /opt/mistri/backup.sh
sudo chmod +x /opt/mistri/backup.sh
sudo -u mistri /opt/mistri/backup.sh      # run it once by hand first
sudo crontab -u mistri -e                     # 15 2 * * * /opt/mistri/backup.sh
```

It uses SQLite's own `.backup` rather than `cp`, because the service is running
and copying a live file can catch it mid-write. It then opens the copy to prove
it is readable, compresses it, and keeps 30 days.

**Copy them off the box.** rclone, scp, anything. On the VPS alone they protect
against a mistake, not against losing the machine.

## When something is wrong

| Symptom | Look at |
|---|---|
| Webhook verification fails | `META_VERIFY_TOKEN`, and that nginx forwards `/webhook` |
| Every webhook returns 401 | `META_APP_SECRET` is wrong or empty; on a BSP, `WEBHOOK_TOKEN` missing from the callback URL |
| `/admin` returns 503 | `ADMIN_PASSWORD` is still `change-me` |
| Bot silent for one customer | `/admin/` shows whether it is paused or handed over |
| Bot silent for everyone | Someone sent `/bot off`. Send `/bot on` from the owner's number |
| Replies always hand over | `ANTHROPIC_API_KEY`, then `journalctl` for the reason |
| Reminders never arrive | Templates not approved in Meta yet; the log names which one failed |
| Duplicate replies | More than one worker running, or nginx timing out and Meta redelivering |
| One chat goes quiet after a lot of messages | The daily reply cap (`MAX_REPLIES_PER_DAY`, default 40). The owner was told; `/bot on <number>` resumes it |
