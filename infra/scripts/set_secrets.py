import os
import secrets

env_path = "/opt/1C/.env.production"
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        lines = f.readlines()
else:
    lines = []

jwt_secret = secrets.token_hex(32)
pg_pass = secrets.token_hex(32)
redis_pass = secrets.token_hex(32)

new_keys = {
    "JWT_SECRET_KEY": jwt_secret,
    "POSTGRES_PASSWORD": pg_pass,
    "REDIS_PASSWORD": redis_pass,
    "PGPASSWORD": pg_pass,
    "DATABASE_URL": f"postgresql+asyncpg://matcher:{pg_pass}@db:5432/matcher",
    "REDIS_URL": f"redis://:{redis_pass}@redis:6379"
}

out_lines = []
for line in lines:
    if "=" in line:
        key = line.split("=")[0].strip()
        if key in new_keys:
            out_lines.append(f"{key}={new_keys.pop(key)}\n")
            continue
    out_lines.append(line)

for k, v in new_keys.items():
    out_lines.append(f"{k}={v}\n")

with open(env_path, "w") as f:
    f.writelines(out_lines)

print("Secrets updated successfully in /opt/1C/.env.production")
