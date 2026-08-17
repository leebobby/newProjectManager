"""重置某个本地账户的登录密码（忘记密码时的救急脚本）。

用法（在 backend 目录下，激活 venv 后执行）：
    python scripts/reset_password.py                    # 把 admin 重置为 admin123
    python scripts/reset_password.py admin 新密码
    python scripts/reset_password.py zhangsan 新密码

只依赖 bcrypt + 标准库 sqlite3，不走 SQLAlchemy，因此不受启动目录影响，
也不需要后端处于停止状态（WAL 模式下写入是安全的，改完下次登录即生效）。
"""
import pathlib
import sqlite3
import sys

import bcrypt

DB_PATH = pathlib.Path(__file__).resolve().parent.parent / "app.db"


def main() -> int:
    username = sys.argv[1] if len(sys.argv) > 1 else "admin"
    password = sys.argv[2] if len(sys.argv) > 2 else "admin123"

    if not DB_PATH.exists():
        sys.stderr.write(f"找不到数据库：{DB_PATH}\n")
        return 1

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT id, role, is_active, can_login FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if not row:
            sys.stderr.write(f"用户不存在：{username}\n")
            names = [r[0] for r in cur.execute(
                "SELECT username FROM users ORDER BY id LIMIT 20").fetchall()]
            sys.stderr.write("现有账户：" + ", ".join(names) + "\n")
            return 1

        uid, role, is_active, can_login = row
        # 顺手解封：只重置密码但账户被停用的话，登录照样失败，排查起来很费时间。
        cur.execute(
            "UPDATE users SET password_hash = ?, is_active = 1, can_login = 1 WHERE id = ?",
            (hashed, uid),
        )
        conn.commit()
    finally:
        conn.close()

    print(f"已重置 {username}（id={uid}, role={role}）的密码为：{password}")
    if not is_active or not can_login:
        print("该账户原本处于停用/禁止登录状态，已一并恢复。")
    print("请登录后立即在「用户管理」中修改密码。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
