import os
import sqlite3
import json
import face_recognition
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.core.handlers.wsgi import WSGIHandler
from django.urls import path
from django import conf
from django.views.decorators.csrf import csrf_exempt

# Configure Django settings
conf.settings.configure(
    DEBUG=True,
    SECRET_KEY='secret',
    ROOT_URLCONF=__name__,
    INSTALLED_APPS=[
        'corsheaders',
    ],
    MIDDLEWARE=[
        'corsheaders.middleware.CorsMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
    ],
    CORS_ALLOWED_ORIGINS=[
        'http://localhost:8080',
    ],
    CORS_ALLOW_METHODS=[
        'GET',
        'POST',
        'OPTIONS',
    ],
    CORS_ALLOW_HEADERS=[
        'content-type',
        'x-csrftoken',
    ],
    DATABASES={
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.path.join(os.path.dirname(__file__), 'db.sqlite3'),
        }
    },
)

def get_db_connection():
    return sqlite3.connect(os.path.join(os.path.dirname(__file__), 'db.sqlite3'))

def fetch_known_faces():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name, face_encoding, Admin FROM known_faces")
        results = []
        for name, encoding_str, admin in cursor.fetchall():
            try:
                encoding = [float(v) for v in encoding_str.split(',')]
                results.append((name, encoding, admin))
            except ValueError:
                print(f"Corrupted encoding for {name}, skipping.")
        return results
    except Exception as e:
        print(f"Database error: {e}")
        return []
    finally:
        if conn:
            conn.close()

@csrf_exempt
def process_image(request):
    if request.method == 'OPTIONS':
        return JsonResponse({'status': 'ok'}, status=200)

    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=400)

    try:
        image = request.FILES['image']
        temp_file = f"temp_{image.name}"
        with open(temp_file, 'wb+') as f:
            for chunk in image.chunks():
                f.write(chunk)

        img = face_recognition.load_image_file(temp_file)
        encodings = face_recognition.face_encodings(img)
        os.remove(temp_file)

        if not encodings:
            return JsonResponse({'result': 'No face detected'})

        known_faces = fetch_known_faces()
        matches = face_recognition.compare_faces([e[1] for e in known_faces], encodings[0])

        if True in matches:
            match_index = matches.index(True)
            name = known_faces[match_index][0]
            admin = known_faces[match_index][2]
            if admin == 1:
                return JsonResponse({'result': f"Match found: {name}", 'redirect': '/AdminPanel'})
            return JsonResponse({'result': f"Match found: {name}"})
        return JsonResponse({'result': 'No matching face found'})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def enroll_face(request):
    if request.method == 'OPTIONS':
        return JsonResponse({'status': 'ok'}, status=200)

    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=400)

    try:
        image = request.FILES['image']
        name = request.POST['name']
        admin = int(request.POST['admin'])

        if not name:
            return JsonResponse({'error': 'Name is required'}, status=400)

        temp_file = f"temp_{image.name}"
        with open(temp_file, 'wb+') as f:
            for chunk in image.chunks():
                f.write(chunk)

        img = face_recognition.load_image_file(temp_file)
        encodings = face_recognition.face_encodings(img)
        os.remove(temp_file)

        if not encodings:
            return JsonResponse({'result': 'No face detected'}, status=400)

        new_encoding = encodings[0]
        known_faces = fetch_known_faces()
        known_encodings = [face[1] for face in known_faces]
        matches = face_recognition.compare_faces(known_encodings, new_encoding, tolerance=0.45)

        if True in matches:
            matched_name = known_faces[matches.index(True)][0]
            return JsonResponse({
                'result': 'Your face already Registered you cannot Enroll your Face again.',
                'message': f"Your face is already registered with the name '{matched_name}'."
            }, status=409)

        encoding_str = ','.join(map(str, new_encoding))

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO known_faces (name, face_encoding, Admin) VALUES (?, ?, ?)',
                       (name, encoding_str, admin))
        conn.commit()
        conn.close()

        return JsonResponse({'result': f"Face enrolled successfully: {name}"})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def get_known_faces(request):
    if request.method == 'OPTIONS':
        return JsonResponse({'status': 'ok'}, status=200)

    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid method'}, status=400)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name, Admin FROM known_faces")
        faces = [{'name': name, 'admin': bool(admin)} for name, admin in cursor.fetchall()]
        conn.close()
        return JsonResponse({'faces': faces})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def delete_face(request):
    if request.method == 'OPTIONS':
        return JsonResponse({'status': 'ok'}, status=200)

    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=400)

    try:
        data = json.loads(request.body)
        name = data.get('name')

        if not name:
            return JsonResponse({'error': 'Name is required'}, status=400)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM known_faces WHERE LOWER(name) = LOWER(?)', (name,))
        if cursor.rowcount == 0:
            conn.close()
            return JsonResponse({'error': f"No face found with name: {name}"}, status=404)
        conn.commit()
        conn.close()

        return JsonResponse({'result': f"Face deleted successfully: {name}"})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def update_face(request):
    if request.method == 'OPTIONS':
        return JsonResponse({'status': 'ok'}, status=200)

    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=400)

    try:
        data = json.loads(request.body)
        old_name = data.get('old_name')
        new_name = data.get('new_name')
        admin = int(data.get('admin'))

        if not old_name or not new_name:
            return JsonResponse({'error': 'Both old_name and new_name are required'}, status=400)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE known_faces SET name = ?, Admin = ? WHERE LOWER(name) = LOWER(?)',
                       (new_name, admin, old_name))
        if cursor.rowcount == 0:
            conn.close()
            return JsonResponse({'error': f"No face found with name: {old_name}"}, status=404)

        conn.commit()
        conn.close()

        return JsonResponse({
            'result': f"Name and Admin status updated successfully: {old_name} → {new_name}, Admin: {admin}"
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def serve_admin_panel(request):
    try:
        with open(os.path.join(os.path.dirname(__file__), 'AdminPanel.html'), 'r') as f:
            return HttpResponse(f.read())
    except FileNotFoundError:
        return HttpResponse("AdminPanel.html not found", status=404)

urlpatterns = [
    path('', lambda _: JsonResponse({'status': 'OK'})),
    path('process-image/', process_image),
    path('enroll-face/', enroll_face),
    path('get-known-faces/', get_known_faces),
    path('delete-face/', delete_face),
    path('update-face/', update_face),
    path('AdminPanel', serve_admin_panel),
]

application = WSGIHandler()

if __name__ == "__main__":
    from django.core.management import execute_from_command_line
    execute_from_command_line()
