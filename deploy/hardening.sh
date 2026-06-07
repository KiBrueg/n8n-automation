#!/usr/bin/env bash
# ============================================================
# Базовый hardening Ubuntu-сервера (Hetzner CX, 4 ГБ RAM).
# Запускать ОДИН раз на свежем сервере от root:
#   bash hardening.sh <username> "<ssh-public-key>"
#
# Делает:
#   - apt update/upgrade
#   - создаёт sudo-пользователя с твоим SSH-ключом
#   - выключает root-логин и парольную аутентификацию по SSH
#   - ufw: разрешает только 22/80/443
#   - fail2ban против брутфорса SSH
#   - unattended-upgrades (авто security-патчи)
#   - 2 ГБ swap (страховка для 4 ГБ RAM)
#   - ставит Docker Engine + compose-plugin
#
# ВАЖНО: не закрывай текущую SSH-сессию, пока не проверишь вход новым
# пользователем по ключу в ОТДЕЛЬНОМ окне — иначе рискуешь запереть себя.
# ============================================================
set -euo pipefail

USERNAME="${1:?Укажи имя пользователя: bash hardening.sh <user> \"<ssh-key>\"}"
SSH_PUBKEY="${2:?Укажи публичный SSH-ключ вторым аргументом (в кавычках)}"

log() { echo -e "\n\033[1;32m==> $*\033[0m"; }

if [[ "$EUID" -ne 0 ]]; then
	echo "Запускай от root." >&2
	exit 1
fi

log "Обновление пакетов"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y

log "Установка базовых утилит"
apt-get install -y ufw fail2ban unattended-upgrades ca-certificates curl gnupg lsb-release

# --- Пользователь + SSH-ключ ---
if ! id "$USERNAME" &>/dev/null; then
	log "Создаю пользователя $USERNAME"
	adduser --disabled-password --gecos "" "$USERNAME"
fi
usermod -aG sudo "$USERNAME"
# пользователь создан без пароля (вход только по ключу) → даём passwordless sudo,
# иначе sudo недоступен (нечем подтвердить). Для деплой-сервера это норма.
echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/90-$USERNAME"
chmod 440 "/etc/sudoers.d/90-$USERNAME"
install -d -m 700 -o "$USERNAME" -g "$USERNAME" "/home/$USERNAME/.ssh"
echo "$SSH_PUBKEY" > "/home/$USERNAME/.ssh/authorized_keys"
chmod 600 "/home/$USERNAME/.ssh/authorized_keys"
chown "$USERNAME:$USERNAME" "/home/$USERNAME/.ssh/authorized_keys"

# passwordless sudo не включаем намеренно (безопаснее)

# --- SSH hardening ---
log "Настройка SSH (запрет root + паролей)"
SSHD_DROPIN=/etc/ssh/sshd_config.d/99-hardening.conf
cat > "$SSHD_DROPIN" <<EOF
PermitRootLogin no
PasswordAuthentication no
ChallengeResponseAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
X11Forwarding no
MaxAuthTries 3
EOF
sshd -t
systemctl restart ssh || systemctl restart sshd

# --- Firewall ---
log "Настройка UFW (22/80/443)"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# --- fail2ban ---
log "Включение fail2ban для SSH"
cat > /etc/fail2ban/jail.local <<EOF
[sshd]
enabled = true
port = 22
maxretry = 4
bantime = 1h
findtime = 10m
EOF
systemctl enable --now fail2ban
systemctl restart fail2ban

# --- Авто security-обновления ---
log "Включение unattended-upgrades"
echo 'APT::Periodic::Update-Package-Lists "1";' > /etc/apt/apt.conf.d/20auto-upgrades
echo 'APT::Periodic::Unattended-Upgrade "1";' >> /etc/apt/apt.conf.d/20auto-upgrades

# --- Swap (страховка для 4 ГБ RAM) ---
if ! swapon --show | grep -q '/swapfile'; then
	log "Создаю 2 ГБ swap"
	fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
	chmod 600 /swapfile
	mkswap /swapfile
	swapon /swapfile
	echo '/swapfile none swap sw 0 0' >> /etc/fstab
	sysctl -w vm.swappiness=10
	echo 'vm.swappiness=10' > /etc/sysctl.d/99-swappiness.conf
fi

# --- Docker ---
if ! command -v docker &>/dev/null; then
	log "Установка Docker Engine + compose-plugin"
	install -m 0755 -d /etc/apt/keyrings
	curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
	chmod a+r /etc/apt/keyrings/docker.gpg
	echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
	apt-get update -y
	apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
usermod -aG docker "$USERNAME"
systemctl enable --now docker

log "Готово. Проверь вход: ssh ${USERNAME}@<IP> в ОТДЕЛЬНОМ окне, ДО закрытия этой сессии."
echo "Дальше: su - ${USERNAME}, git clone репозитория, cp .env.example .env, ./deploy/deploy.sh"
