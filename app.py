from flask import Flask, request, jsonify
import os
import uuid  # Importa uuid para generar identificadores únicos
from flask_cors import CORS
import base64
from io import BytesIO
from PIL import Image
from werkzeug.utils import secure_filename
from openai import OpenAI
import json
from dotenv import load_dotenv

app = Flask(__name__)
CORS(app)


#Carga las variables de entorno
load_dotenv()

# Configuración de los Saludos

saludos_por_idioma = {
    "en-US": "Hello",
    "sv-SE": "Hallå",
    "es-ES": "Hola",
    "pt-BR": "Olá",
}

# Almacenamiento en memoria para las respuestas procesadas
processed_images = {}


openIA_api_key = os.getenv('IMAGES_API_KEY')
print(openIA_api_key)
client = OpenAI(
    api_key=openIA_api_key,
)
# Crea el asistente
ass_id = os.getenv('IMAGES_ASS_ID')
print(ass_id)
assistant = client.beta.assistants.retrieve(ass_id)                                            
instruc = assistant.instructions

# Configuración para la carga de archivos
UPLOAD_FOLDER = 'uploads/'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_image_from_base64(data, filename):
    image_data = base64.b64decode(data)
    image = Image.open(BytesIO(image_data))
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    image.save(filepath)
    return filepath

def call_openai_assistant(file,saludo):

    # Crea el archivo
    file_creation_response = client.files.create(
        file=file,
        purpose='assistants'
    )
    print(file_creation_response)
    #Crea el hilo
    thread = client.beta.threads.create(
        messages=[
            {
                "role":"user",
                "content": [
                    {
                        "type":"text",
                        "text":saludo
                    },
                    {
                        "type": "image_file",
                        "image_file": {"file_id": file_creation_response.id}
                    },
                    
                ]
             
            }
        ]
    )

    # Crea y ejecuta el run

    run = client.beta.threads.runs.create(
    thread_id=thread.id,
    assistant_id=assistant.id,
    instructions=instruc
    )

    status = "in_progress"
    while status == "queued" or status == "in_progress" or status == "requires_action":
        run = client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id
        )
        status = run.status
        #print(status)

    thread_messages = client.beta.threads.messages.list(thread.id)
    #return {'mensaje':thread_messages,'fin_conversacion' : fin_conversacion,'run':run}
    response = thread_messages.data[0].content[0].text.value
    return response

@app.route('/upload', methods=['POST'])
def upload_image():
    data = request.json
    if 'image' not in data or 'filename' not in data:
        return jsonify({'status': 'error', 'message': 'Missing image or filename data'}), 400
    original_filename = secure_filename(data['filename'])
    if allowed_file(original_filename):
        # Genera un ID único para la imagen
        image_id = str(uuid.uuid4()) + '.' + original_filename.rsplit('.', 1)[1]
        filepath = save_image_from_base64(data['image'], image_id)
        return jsonify({'status': 'success', 'message': 'Image uploaded successfully', 'data': {'image_id': image_id}}), 201
    else:
        return jsonify({'status': 'error', 'message': 'Invalid file type'}), 400

@app.route('/process/<image_id>/<language>', methods=['GET'])
def process_image(image_id, language):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(image_id))
    cache_key = (image_id, language)  # Usar una tupla para la clave compuesta
    print(cache_key)
    if os.path.exists(file_path):
        try:
            with open(file_path, "rb") as file:
                if cache_key in processed_images:
                    return jsonify(processed_images[cache_key]), 200
                else:
                    saludo = saludos_por_idioma.get(language, "Hola")  # Saludo predeterminado
                    response = call_openai_assistant(file, saludo)
                    response_dict = json.loads(response)
                    processed_images[cache_key] = response_dict  # Guardar en caché
                    return jsonify(response_dict), 200
        except IOError:
            return jsonify({'status': 'error', 'message': 'Failed to process image'}), 500
    else:
        return jsonify({'status': 'error', 'message': 'Image not found'}), 404

    
@app.route('/results/<image_id>/<language>', methods=['GET'])
def get_results(image_id, language):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(image_id))
    cache_key = (image_id, language)  # Usar una tupla para la clave compuesta
    print(cache_key)

    if os.path.exists(file_path):
        if cache_key in processed_images:
            return jsonify(processed_images[cache_key]), 200
        else:
            try:
                with open(file_path, "rb") as file:
                    saludo = saludos_por_idioma.get(language, "Hola")
                    response = call_openai_assistant(file, saludo)
                    response_dict = json.loads(response)
                    processed_images[cache_key] = response_dict  # Guardar en caché si no estaba
                    return jsonify(response_dict), 200
            except IOError:
                return jsonify({'status': 'error', 'message': 'Failed to process image'}), 500
    else:
        return jsonify({'status': 'error', 'message': 'Image not found'}), 404

    
@app.route('/delete/<image_id>', methods=['DELETE'])
def delete_image(image_id):
    # Construye el path completo donde se encuentra la imagen
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(image_id))
    
    # Comprobar si el archivo existe
    if os.path.exists(file_path):
        try:
            # Elimina el archivo del sistema
            os.remove(file_path)
            return jsonify({'status': 'success', 'message': 'Image and results deleted successfully'}), 200
        except Exception as e:
            # Manejo de cualquier excepción que pueda ocurrir durante la eliminación
            return jsonify({'status': 'error', 'message': 'Error deleting the image', 'details': str(e)}), 500
    else:
        # Si el archivo no existe, devuelve un error
        return jsonify({'status': 'error', 'message': 'Image not found'}), 404

   
if __name__ == '__main__':
    app.run(debug=True)
