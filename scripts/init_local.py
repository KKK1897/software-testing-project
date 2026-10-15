"""只初始化本项目独立 MySQL；不允许传入其它主机、端口或库。"""
import json
import secrets
from pathlib import Path
import pymysql

ROOT = Path(__file__).resolve().parents[1]
cfg_file = ROOT / 'runtime/local.json'
if cfg_file.exists():
    raise SystemExit('已有配置，拒绝覆盖或重复初始化。')
conn = pymysql.connect(host='127.0.0.1', port=13306, user='root', password='', autocommit=True)
with conn.cursor() as cur:
    cur.execute('SELECT @@datadir')
    actual = Path(cur.fetchone()[0]).resolve()
    assert actual == (ROOT / 'runtime/mysql-data').resolve(), actual
    cur.execute("CREATE DATABASE jsh_erp_qa CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci")
    conn.select_db('jsh_erp_qa')
    sql = (ROOT / 'upstream/jshERP/jshERP-boot/docs/jsh_erp.sql').read_text(encoding='utf-8')
    # 上游初始化脚本没有存储过程；逐条执行，严格遇错中止。
    for statement in sql.split(';'):
        if statement.strip():
            cur.execute(statement)
    db_password = secrets.token_hex(20)
    redis_password = secrets.token_hex(20)
    cur.execute("CREATE USER 'erpqa'@'127.0.0.1' IDENTIFIED WITH mysql_native_password BY %s", (db_password,))
    cur.execute("GRANT ALL ON jsh_erp_qa.* TO 'erpqa'@'127.0.0.1'")
    cur.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (secrets.token_hex(24),))
cfg_file.write_text(json.dumps({'db_password': db_password, 'redis_password': redis_password}), encoding='utf-8')
(ROOT / 'runtime/redis.conf').write_text(f'bind 127.0.0.1\nport 16379\nrequirepass {redis_password}\nsave ""\nappendonly no\n', encoding='ascii')
(ROOT / 'runtime/application.properties').write_text(
    f'server.address=127.0.0.1\nserver.port=9999\n'
    f'spring.datasource.url=jdbc:mysql://127.0.0.1:13306/jsh_erp_qa?useUnicode=true&characterEncoding=utf8&useSSL=false&allowMultiQueries=true\n'
    f'spring.datasource.username=erpqa\nspring.datasource.password={db_password}\n'
    f'spring.redis.port=16379\nspring.redis.password={redis_password}\n'
    "spring.datasource.hikari.connection-init-sql=SET SESSION sql_mode=(SELECT REPLACE(@@sql_mode,'ONLY_FULL_GROUP_BY',''))\n"
    f'file.path={ROOT.as_posix()}/runtime/upload\nserver.tomcat.basedir={ROOT.as_posix()}/runtime/tomcat\n', encoding='utf-8')
print('初始化完成；随机凭据仅保存于被忽略的 runtime/。')
