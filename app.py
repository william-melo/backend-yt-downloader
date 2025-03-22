from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import uuid
import logging
import threading
import time
from pathlib import Path
from datetime import datetime

app = Flask(__name__)
CORS(app, origins=os.getenv('CORS_ORIGIN', '*'))

# Configuración
DOWNLOAD_FOLDER = Path('./downloads')
DOWNLOAD_FOLDER.mkdir(exist_ok=True)
CLEANUP_INTERVAL = 3600
FILE_MAX_AGE = 86400

# URL base del servidor
BASE_URL = os.getenv('BASE_URL', 'http://localhost:5000')

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Opciones de formato mejoradas
# Near the top of your file, update the FORMAT_OPTIONS dictionary
FORMAT_OPTIONS = {
    'best': {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'no_warnings': True,
        'ignoreerrors': True,
        'nocheckcertificate': True,
        'geo_bypass': True,
    },
    '1080p': {
        'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best',
        'no_warnings': True,
        'ignoreerrors': True,
        'nocheckcertificate': True,
        'geo_bypass': True,
    },
    '720p': {'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best'},
    '480p': {'format': 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best'},
    '360p': {'format': 'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best'},
    'audio': {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': '%(title)s.%(ext)s',
        'restrictfilenames': True
    }
}

# Función para limpiar archivos antiguos
def cleanup_old_files():
    while True:
        try:
            logger.info(f"Iniciando limpieza programada: {datetime.now()}")
            current_time = time.time()
            deleted_files = 0
            
            for file_path in DOWNLOAD_FOLDER.glob('*'):
                file_age = current_time - file_path.stat().st_mtime
                if file_age > FILE_MAX_AGE:
                    try:
                        file_path.unlink()
                        deleted_files += 1
                        logger.info(f"Eliminado archivo antiguo: {file_path}")
                    except Exception as e:
                        logger.error(f"Error al eliminar archivo {file_path}: {str(e)}")
            
            if deleted_files > 0:
                logger.info(f"Limpieza completada: {deleted_files} archivos eliminados")
            else:
                logger.info("Limpieza completada: no se encontraron archivos antiguos")
                
            # Esperar hasta el próximo intervalo de limpieza
            time.sleep(CLEANUP_INTERVAL)
        except Exception as e:
            logger.error(f"Error en el proceso de limpieza automática: {str(e)}")
            # Si ocurre un error, esperar antes de reintentar
            time.sleep(300)  # 5 minutos

@app.route('/download', methods=['POST'])
def download_video():
    try:
        data = request.json
        video_url = data.get('url')
        format_option = data.get('format', 'best')
        
        if not video_url:
            return jsonify({'error': True, 'message': 'URL no proporcionada'}), 400

        # Verificar que sea una URL de YouTube
        if 'youtube.com' not in video_url and 'youtu.be' not in video_url:
            return jsonify({'error': True, 'message': 'URL no válida de YouTube'}), 400

        # Crear un ID único para este archivo
        file_id = str(uuid.uuid4())
        file_path = DOWNLOAD_FOLDER / file_id
        
        logger.info(f"Iniciando descarga: {video_url} con formato {format_option}")
        
        # Manejo especial para audio
        if format_option == 'audio':
            # Configuración específica para audio
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': f'{file_path}.%(ext)s',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'restrictfilenames': True,
                'quiet': False,
                'no_warnings': True,
                'ignoreerrors': True,
                'nocheckcertificate': True,
                'geo_bypass': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                video_title = info.get('title', 'audio')
                
                # Buscar el archivo de audio descargado
                audio_file = Path(f"{file_path}.mp3")
                if not audio_file.exists():
                    # Intentar encontrar cualquier archivo creado con el ID
                    possible_files = list(DOWNLOAD_FOLDER.glob(f"{file_id}.*"))
                    if possible_files:
                        audio_file = possible_files[0]
                    else:
                        raise FileNotFoundError("No se pudo encontrar el archivo de audio descargado")
                
                safe_title = video_title.replace(' ', '_').replace('/', '_').replace('\\', '_')
                final_filename = f"{safe_title}.mp3"
                
                # Crear URL de descarga completa
                download_url = f"{BASE_URL}/download/{audio_file.name}?filename={final_filename}"
                
                return jsonify({
                    'success': True,
                    'title': video_title,
                    'download_url': download_url
                })
        else:
            # Para videos, mantener el código original
            ydl_opts = FORMAT_OPTIONS.get(format_option, FORMAT_OPTIONS['best']).copy()
            if isinstance(ydl_opts, dict) and 'postprocessors' not in ydl_opts:
                ydl_opts.update({
                    'outtmpl': f'{file_path}.%(ext)s',
                    'quiet': False,
                    'no_warnings': False,
                    'progress': True,
                    'merge_output_format': 'mp4'
                })
            
            # Descargar video
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                video_title = info.get('title', 'video')
                download_file = f"{file_path}.mp4"
                final_filename = f"{video_title}.mp4"
                
                # Verificar que el archivo existe
                download_path = Path(download_file)
                if not download_path.exists():
                    # Buscar cualquier archivo que comience con el file_id
                    potential_files = list(DOWNLOAD_FOLDER.glob(f"{file_id}.*"))
                    if potential_files:
                        download_path = potential_files[0]
                    else:
                        raise FileNotFoundError("No se pudo encontrar el archivo descargado")
                
                # Crear URL de descarga completa
                download_url = f"{BASE_URL}/download/{download_path.name}?filename={final_filename}"
                
                return jsonify({
                    'success': True,
                    'title': video_title,
                    'download_url': download_url
                })
            
    except Exception as e:
        logger.error(f"Error en la descarga: {str(e)}")
        return jsonify({'error': True, 'message': f'Error: {str(e)}'}), 500

@app.route('/download/<filename>')
def serve_file(filename):
    try:
        file_path = DOWNLOAD_FOLDER / filename
        final_filename = request.args.get('filename', filename)
        
        if not file_path.exists():
            return jsonify({'error': True, 'message': 'Archivo no encontrado'}), 404
        
        # Determinar el tipo de contenido basado en la extensión
        mimetype = None  # Dejar que Flask determine el tipo automáticamente
        if filename.endswith('.mp4'):
            mimetype = 'video/mp4'
        elif filename.endswith('.mp3'):
            mimetype = 'audio/mpeg'
        elif filename.endswith('.m4a'):
            mimetype = 'audio/mp4'
            
        # Enviar el archivo con los encabezados adecuados
        return send_file(
            path_or_file=str(file_path),
            mimetype=mimetype,
            as_attachment=True,
            download_name=final_filename,
            conditional=True
        )
    except Exception as e:
        logger.error(f"Error al servir el archivo: {str(e)}")
        return jsonify({'error': True, 'message': f'Error: {str(e)}'}), 500

@app.route('/health')
def health_check():
    return jsonify({'status': 'ok'})
  
@app.route('/video-info', methods=['POST'])
def get_video_info():
    try:
        data = request.json
        video_url = data.get('url')
        
        if not video_url:
            return jsonify({'success': False, 'message': 'URL not provided'}), 400

        # Verify it's a YouTube URL
        if 'youtube.com' not in video_url and 'youtu.be' not in video_url:
            return jsonify({'success': False, 'message': 'Not a valid YouTube URL'}), 400

        # Configure yt-dlp with additional options
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'ignoreerrors': True,
            'nocheckcertificate': True,
            'geo_bypass': True,
            'extract_flat': 'in_playlist'
        }

        # Get video information
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            
            # Convert duration to readable format
            duration_seconds = info.get('duration', 0)
            hours = duration_seconds // 3600
            minutes = (duration_seconds % 3600) // 60
            seconds = duration_seconds % 60
            
            if hours > 0:
                duration = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                duration = f"{minutes:02d}:{seconds:02d}"

            return jsonify({
                'success': True,
                'title': info.get('title', 'Unknown Title'),
                'channel': info.get('channel', 'Unknown Channel'),
                'duration': duration,
                'thumbnail': info.get('thumbnail', ''),
            })

    except Exception as e:
        logger.error(f"Error getting video info: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500
        
@app.route('/video-qualities', methods=['POST'])
def get_video_qualities():
    try:
        data = request.json
        video_url = data.get('url')
        
        if not video_url:
            return jsonify({'success': False, 'message': 'URL not provided'}), 400

        # Verify it's a YouTube URL
        if 'youtube.com' not in video_url and 'youtu.be' not in video_url:
            return jsonify({'success': False, 'message': 'Not a valid YouTube URL'}), 400

        # Configure yt-dlp to extract only format information
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'nocheckcertificate': True,
            'geo_bypass': True,
        }

        # Get video formats
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            formats = info.get('formats', [])
            
            # Define desired resolutions including 4K
            desired_resolutions = [2160, 1080, 720, 480, 360]
            processed_formats = []
            seen_resolutions = set()
            max_height = 0
            
            # Process formats
            for f in formats:
                # Skip formats without video
                if not f.get('height'):
                    continue
                    
                height = f.get('height', 0)
                max_height = max(max_height, height)
                
                # Only process desired resolutions
                if height not in desired_resolutions:
                    continue
                
                filesize = f.get('filesize', 0)
                resolution = f'{f.get("width", "?")}x{height}'
                
                # Skip if we've already seen this resolution
                if resolution in seen_resolutions:
                    continue
                seen_resolutions.add(resolution)
                
                quality = {
                    'id': f'{height}p',
                    'label': '4K' if height == 2160 else 'Full HD' if height == 1080 else 'HD' if height == 720 else 'SD' if height == 480 else 'Low',
                    'resolution': resolution,
                    'fileSize': f'{filesize / 1024 / 1024:.1f}MB' if filesize else 'Unknown'
                }
                processed_formats.append(quality)
            
            # Sort formats by resolution (highest first)
            processed_formats.sort(key=lambda x: int(x['id'].replace('p', '')), reverse=True)
            
            # Add 'best' quality option at the top if we have any formats
            if processed_formats:
                best_quality = processed_formats[0]  # Highest available quality
                best_option = {
                    'id': 'best',
                    'label': 'Best',
                    'resolution': best_quality['resolution'],
                    'fileSize': best_quality['fileSize']
                }
                processed_formats.insert(0, best_option)

            return jsonify({
                'success': True,
                'qualities': processed_formats
            })

    except Exception as e:
        logger.error(f"Error getting video qualities: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

if __name__ == '__main__':
    # Iniciar el hilo de limpieza automática
    cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
    cleanup_thread.start()
    logger.info("Iniciado proceso de limpieza automática en segundo plano")
    
    # Iniciar el servidor Flask
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)