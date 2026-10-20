import os, sys, json, time
from pathlib import Path
from datetime import date
ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/'data'/'ittokai_v20_5_scale.db'
if DB.exists(): DB.unlink()
os.environ['DATABASE_URL']=f'sqlite:///{DB}'
sys.path.insert(0,str(ROOT))
import server

start=time.perf_counter()
dummy_hash=server.hash_password('x')
with server.SessionLocal() as s:
    # Reset seeded demo and build target-scale synthetic set while preserving schema.
    # Keep seeded facility; add to total 50.
    facilities=s.query(server.Facility).all()
    while len(facilities)<50:
        i=len(facilities)+1
        f=server.Facility(code=f'F{i:02d}',name=f'テスト施設{i:02d}')
        s.add(f); s.flush(); facilities.append(f)
    # Keep seeded users, but create exactly 20 workforce records and 40 family accounts per facility for workload.
    for fi,f in enumerate(facilities,1):
        dep=s.query(server.Department).filter_by(facility_id=f.id).first()
        if not dep:
            dep=server.Department(facility_id=f.id,name='入所',code='ADMISSION'); s.add(dep); s.flush()
        existing=s.query(server.User).filter(server.User.facility_id==f.id,server.User.role.in_(['staff','middle_manager','admin'])).count()
        for j in range(existing,20):
            role='admin' if j==0 else ('middle_manager' if j<5 else 'staff')
            u=server.User(name=f'職員{fi:02d}-{j:02d}',email=f'w{fi:02d}_{j:02d}@scale.local',employee_code=f'E{fi:02d}{j:02d}',password_hash=dummy_hash,role=role,facility_id=f.id,department_id=dep.id)
            s.add(u); s.flush()
            # two statutory leave lots; previous lot is close enough to expose expiration management
            s.add_all([
                server.LeaveGrant(user_id=u.id,grant_date='2025-04-01',granted_days=20,remaining_days=4+(j%3),taken_days=16-(j%3),expires_on='2027-03-31',source='scale'),
                server.LeaveGrant(user_id=u.id,grant_date='2026-04-01',granted_days=20,remaining_days=15+(j%5),taken_days=5-(j%5 if j%5<5 else 0),expires_on='2028-03-31',source='scale')
            ])
            # six months work-time totals, stored as one synthetic aggregate row/month
            months=['2026-05-01','2026-06-01','2026-07-01','2026-08-01','2026-09-01','2026-10-01']
            for mi,wd in enumerate(months):
                overtime=(28 + ((j+mi)%25))*60
                holiday=((j+mi)%8)*30
                s.add(server.WorkTimeRecord(user_id=u.id,work_date=wd,overtime_minutes=overtime,holiday_minutes=holiday,source='chronos'))
        fam_existing=s.query(server.User).filter_by(facility_id=f.id,role='family').count()
        for j in range(fam_existing,40):
            fam=server.User(name=f'家族{fi:02d}-{j:02d}',email=f'f{fi:02d}_{j:02d}@scale.local',password_hash=dummy_hash,role='family',facility_id=f.id)
            s.add(fam); s.flush()
            res=server.Resident(resident_code=f'R{fi:02d}{j:02d}',facility_id=f.id,name=f'利用者{fi:02d}-{j:02d}',service_type='入所')
            s.add(res); s.flush(); s.add(server.FamilyLink(user_id=fam.id,resident_id=res.id,relation='家族',is_primary=1))
    s.commit()
seed_seconds=time.perf_counter()-start

calc_start=time.perf_counter()
facility_reports=[]
with server.SessionLocal() as s:
    for f in s.query(server.Facility).order_by(server.Facility.id).all():
        admin=s.query(server.User).filter_by(facility_id=f.id,role='admin').first()
        if not admin:
            admin=s.query(server.User).filter(server.User.facility_id==f.id,server.User.role.in_(['middle_manager','staff'])).first()
        facility_reports.append(server.facility_labor_summary(s,admin))
    hq=server.hq_dashboard(s)
calc_seconds=time.perf_counter()-calc_start

with server.SessionLocal() as s:
    workforce=s.query(server.User).filter(server.User.role.in_(['staff','middle_manager','admin']),server.User.active==1).count()
    families=s.query(server.User).filter_by(role='family',active=1).count()
    facilities_count=s.query(server.Facility).filter_by(active=1).count()
    grants=s.query(server.LeaveGrant).count(); workrows=s.query(server.WorkTimeRecord).count()
    alerts=sum(len(r['alerts']) for r in facility_reports)
    expiring=sum(r['totals']['expiring_leave_days'] for r in facility_reports)

issues=[]
if facilities_count<50: issues.append('facility scale below target')
if workforce<1000: issues.append('workforce scale below target')
if families<2000: issues.append('family scale below target')
if calc_seconds>30: issues.append(f'labor dashboard aggregation too slow: {calc_seconds:.2f}s')
if not alerts: issues.append('alert engine produced no alerts under synthetic high-risk workload')
if expiring<=0: issues.append('expiration projection produced no expiring leave')

report={
 'version':'20.7','target':{'facilities':50,'staff':1000,'families':2000},
 'actual':{'facilities':facilities_count,'staff':workforce,'families':families,'leave_grants':grants,'work_time_rows':workrows},
 'timing_seconds':{'seed':round(seed_seconds,3),'labor_50_facilities':round(calc_seconds,3)},
 'alerts_detected':alerts,'expiring_leave_days':round(expiring,1),'hq':hq,'issues':issues,'result':'PASS' if not issues else 'FAIL'
}
print(json.dumps(report,ensure_ascii=False,indent=2))
(ROOT/'VIRTUAL_SCALE_RESULT_v20.7.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
if issues: raise SystemExit(1)
