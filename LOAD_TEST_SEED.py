"""任意実行: 50施設 / 職員1000 / 家族2000 / 協賛企業100 の規模テストデータを生成。
空の専用テストDBで実行してください。本番環境では実行禁止。
"""
from server import SessionLocal, Facility, Department, User, Resident, FamilyLink, Supplier, hash_password

with SessionLocal() as s:
    if s.query(Facility).count() >= 50 and s.query(User).count() >= 3000:
        print('scale seed already exists'); raise SystemExit(0)
    base=s.query(Facility).filter_by(code='MAISON-NINOMIYA').first()
    facilities=[base]
    for i in range(2,51):
        f=Facility(code=f'FAC-{i:03d}',name=f'テスト施設{i:02d}',corporation='社会福祉法人 一燈会')
        s.add(f); s.flush(); s.add(Department(facility_id=f.id,code='MAIN',name='介護部門')); facilities.append(f)
    # 1000 staff total in addition to built-in demo staff; distribution target: admins 50, middle 200, others 750
    pw_staff=hash_password('LoadTest1234!')
    staff=[]
    for i in range(1,998):
        f=facilities[(i-1)%50]
        role='admin' if i<=49 else ('middle_manager' if i<=248 else 'staff')
        staff.append(User(employee_code=f'L{i:04d}',name=f'負荷テスト職員{i:04d}',email=f'load.staff{i:04d}@example.invalid',password_hash=pw_staff,role=role,facility_id=f.id))
    s.add_all(staff); s.flush()
    pw_family=hash_password('LoadTest1234!')
    families=[]; residents=[]
    for i in range(1,2000):
        f=facilities[(i-1)%50]
        families.append(User(name=f'負荷テスト家族{i:04d}',email=f'load.family{i:04d}@example.invalid',password_hash=pw_family,role='family',facility_id=f.id))
        residents.append(Resident(resident_code=f'LR{i:04d}',facility_id=f.id,name=f'負荷テスト利用者{i:04d}',service_type='入所'))
    s.add_all(families); s.add_all(residents); s.flush()
    s.add_all([FamilyLink(user_id=u.id,resident_id=r.id,relation='家族',is_primary=1) for u,r in zip(families,residents)])
    s.add_all([Supplier(supplier_type='sponsor',name=f'外部協賛企業{i:03d}',code=f'SP-{i:03d}') for i in range(1,100)])
    s.commit()
    print('scale seed completed')
