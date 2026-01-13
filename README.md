# Github

INFO: Iniciando sesión en Cardmarket...

CRITICAL: Bloqueado por Cloudflare. Las IPs de GitHub suelen estar marcadas.

Error: Process completed with exit code 1.

# Cardmarket Exporter (Termux Edition)

Herramienta ligera para exportar tus compras y ventas de Cardmarket a CSV directamente desde Android usando Termux. 

## Características
- **Optimizado para Termux**: No requiere Playwright ni Chromium.
- **Bypass de Cloudflare**: Utiliza tu conexión móvil residencial para evitar bloqueos de IP de centros de datos.
- **Recuperación de Estado**: Detecta pedidos ya exportados para no duplicar datos y retomar donde se dejó.
- **Exportación Segmentada**: Elige entre exportar Compras (Recibidos), Ventas (Enviados) o ambos.

## Instalación en Termux
1. Instala Termux (preferiblemente desde F-Droid).
2. Actualiza los paquetes:
   ```bash
   pkg update && pkg upgrade
   ```
3. Instala Python y dependencias:
   ```bash
   pkg install python
   pip install requests beautifulsoup4
   ```

## Configuración
Define tus credenciales de Cardmarket como variables de entorno:
```bash
export CM_USERNAME="tu_usuario"
export CM_PASSWORD="tu_password"
```

## Uso
Ejecuta el script con las opciones deseadas:
```bash
# Exportar todo lo nuevo de 2025
python export_script.py --include-purchases --include-sales --year 2025

# Solo compras
python export_script.py --include-purchases
```

## Recuperación de Estado
El script lee automáticamente `cardmarket_export.csv`. Si encuentra un ID de pedido que ya existe en el archivo, lo omitirá. Si en una página de Cardmarket todos los pedidos ya existen, el script se detendrá automáticamente asumiendo que ya está al día.
