import os
import secrets

env_path = "/opt/1C/.env.production"
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        lines = f.readlines()
else:
    lines = []

new_keys = {
    "JWT_SECRET_KEY": secrets.token_hex(32),
    "POSTGRES_PASSWORD": secrets.token_hex(32),
    "REDIS_PASSWORD": secrets.token_hex(32)
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
