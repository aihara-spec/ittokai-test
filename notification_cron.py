"""Run ITTOKAI scheduled notification reminders.
Configure APP_BASE_URL and NOTIFICATION_CRON_SECRET in the environment.
Suitable for a Render Cron Job (for example hourly).
"""
import os, json, urllib.request, urllib.error

base=(os.environ.get('APP_BASE_URL') or '').rstrip('/')
secret=os.environ.get('NOTIFICATION_CRON_SECRET') or ''
if not base or not secret:
    raise SystemExit('APP_BASE_URL and NOTIFICATION_CRON_SECRET are required')
req=urllib.request.Request(
    base+'/api/notifications/run-reminders', data=b'', method='POST',
    headers={'x-ittokai-cron-secret':secret,'Content-Type':'application/json'}
)
try:
    with urllib.request.urlopen(req,timeout=30) as res:
        print(res.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    detail=e.read().decode('utf-8','ignore')
    raise SystemExit(f'notification cron failed: HTTP {e.code} {detail}')
