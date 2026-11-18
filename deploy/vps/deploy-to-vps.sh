#!/usr/bin/env bash
set -e

echo "=== Configurando MayorClips en VPS 166.0.112.247 ==="

# 1. Crear directorios de ejecución y media temporal
mkdir -p /opt/mayorclips/publisher /var/www/mc-media
chown -R www-data:www-data /var/www/mc-media
chmod -R 755 /var/www/mc-media

# 2. Configurar base de datos PostgreSQL aislada
sudo -u postgres psql -f /opt/mayorclips/setup-vps-db.sql || true

# 3. Registrar e iniciar servicio daemon systemd
cp /opt/mayorclips/deploy/vps/mayorclips-publisher.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable mayorclips-publisher
systemctl restart mayorclips-publisher

# 4. Configurar cron de recolección de estadísticas (cada 3 horas)
(crontab -l 2>/dev/null | grep -v 'collect-stats'; echo "0 */3 * * * python3 /opt/mayorclips/publisher/stats/collector.py >> /var/log/mayorclips-stats.log 2>&1") | crontab -

echo "=== Despliegue de MayorClips en VPS finalizado exitosamente ==="
