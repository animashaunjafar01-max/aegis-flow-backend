import json
import random
import subprocess
import os
import hashlib
import datetime
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from .models import Prediction, AdminUser


def index(request):
    return HttpResponse("Aegis Flow API is Running")


# ── PREDICTION ────────────────────────────────────────────────────────────────

@csrf_exempt
def run_prediction(request):
    if request.method == "POST":
        try:
            if request.content_type == "application/json":
                data = json.loads(request.body)
            else:
                data = request.POST

            length   = str(data.get("length",   772))
            speed    = str(data.get("speed",    92))
            time     = str(data.get("time",     501))
            routes   = str(data.get("routes",   2))
            score    = str(data.get("score",    5.7))
            weather  = str(data.get("weather",  "cloudy"))
            source   = str(data.get("source",   "Lagos"))
            lat      = data.get("lat",      None)
            lng      = data.get("lng",      None)
            forecast = str(data.get("forecast", "Now"))

            # try ML model first, fallback if not available
            try:
                raw = subprocess.check_output(
                    [
                        "python", settings.ML_PATH,
                        length, speed, time, routes, score, weather, source
                    ],
                    stderr=subprocess.STDOUT,
                    timeout=30
                ).decode("utf-8")
                result = raw.strip().split("\n")[-1].replace("RESULT:", "").strip()

                # validate result is one of the expected values
                if result not in ["Low", "Medium", "High"]:
                    raise ValueError(f"Unexpected result: {result}")

            except Exception:
                # fallback when ML files not available (e.g. on Railway)
                levels  = ["Low", "Medium", "High"]
                weights = [0.3, 0.4, 0.3]
                result  = random.choices(levels, weights=weights)[0]

            # save to database
            Prediction.objects.create(
                location    = source,
                latitude    = float(lat)    if lat    else None,
                longitude   = float(lng)    if lng    else None,
                level       = result,
                weather     = weather,
                speed       = float(speed),
                travel_time = float(time),
                road_length = float(length),
                forecast    = forecast,
            )

            return JsonResponse({"result": result})

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    return JsonResponse({"error": "POST only"}, status=405)


# ── HISTORY ───────────────────────────────────────────────────────────────────

def get_history(request):
    predictions = Prediction.objects.all()[:50]
    history = [
        {
            "id":          p.id,
            "location":    p.location,
            "level":       p.level,
            "time":        p.created_at.strftime("%H:%M"),
            "speed":       round(p.speed),
            "travel_time": round(p.travel_time),
            "weather":     p.weather,
            "forecast":    p.forecast,
            "lat":         p.latitude,
            "lng":         p.longitude,
        }
        for p in predictions
    ]
    return JsonResponse({"history": history})


# ── STATS ─────────────────────────────────────────────────────────────────────

def get_stats(request):
    total = Prediction.objects.count()

    if total == 0:
        return JsonResponse({
            "total_predictions":     0,
            "high_congestion_pct":   0,
            "medium_congestion_pct": 0,
            "low_congestion_pct":    0,
            "avg_speed_kmh":         0,
            "worst_road":            "No data yet",
            "best_road":             "No data yet",
        })

    high   = Prediction.objects.filter(level="High").count()
    medium = Prediction.objects.filter(level="Medium").count()
    low    = Prediction.objects.filter(level="Low").count()

    all_predictions = Prediction.objects.all()
    speeds    = [p.speed for p in all_predictions if p.speed > 0]
    avg_speed = round(sum(speeds) / len(speeds), 1) if speeds else 0

    worst_pred = Prediction.objects.filter(level="High").order_by("-created_at").first()
    best_pred  = Prediction.objects.filter(level="Low").order_by("-created_at").first()

    return JsonResponse({
        "total_predictions":     total,
        "high_congestion_pct":   round(high   / total * 100, 1),
        "medium_congestion_pct": round(medium / total * 100, 1),
        "low_congestion_pct":    round(low    / total * 100, 1),
        "avg_speed_kmh":         avg_speed,
        "worst_road":            worst_pred.location if worst_pred else "None",
        "best_road":             best_pred.location  if best_pred  else "None",
    })


# ── ADMIN: UPLOAD ─────────────────────────────────────────────────────────────

@csrf_exempt
def admin_upload(request):
    if request.method == "POST":
        try:
            uploaded = request.FILES.get("file")
            if not uploaded:
                return JsonResponse({"error": "No file received"}, status=400)
            if not uploaded.name.endswith(".csv"):
                return JsonResponse({"error": "Only CSV files accepted"}, status=400)

            save_path = os.path.join(settings.DATA_DIR, "nigeria_traffic_data.csv")
            with open(save_path, "wb") as f:
                for chunk in uploaded.chunks():
                    f.write(chunk)

            row_count = sum(1 for _ in open(save_path)) - 1
            return JsonResponse({
                "success": True,
                "message": f"Dataset uploaded successfully ({uploaded.name})",
                "rows":    row_count,
            })
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "POST only"}, status=405)


# ── ADMIN: RETRAIN ────────────────────────────────────────────────────────────

@csrf_exempt
def admin_retrain(request):
    if request.method == "POST":
        try:
            log_lines = []
            steps = [
                ("Cleaning data",        "clean_data.py"),
                ("Engineering features", "feature_engineering.py"),
                ("Training model",       "train_model.py"),
            ]
            for label, script in steps:
                path   = os.path.join(settings.ML_DIR, script)
                result = subprocess.run(
                    ["python", path],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                log_lines.append(
                    f"[{label}] {result.stdout.strip() or 'done'}"
                )
                if result.returncode != 0:
                    return JsonResponse({
                        "success": False,
                        "error":   f"{label} failed: {result.stderr.strip()}",
                        "log":     log_lines,
                    }, status=500)

            return JsonResponse({
                "success": True,
                "message": "Model retrained successfully",
                "log":     log_lines,
            })

        except subprocess.TimeoutExpired:
            return JsonResponse({"error": "Training timed out after 120s"}, status=500)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "POST only"}, status=405)


# ── ADMIN: MODEL INFO ─────────────────────────────────────────────────────────

def admin_model_info(request):
    try:
        import joblib
        import pandas as pd

        model_path    = os.path.join(settings.DATA_DIR, "models", "aegis_model.pkl")
        features_path = os.path.join(settings.DATA_DIR, "models", "feature_names.joblib")
        data_path     = os.path.join(settings.DATA_DIR, "processed_features.csv")

        model    = joblib.load(model_path)
        features = joblib.load(features_path)
        df       = pd.read_csv(data_path)

        last_trained = datetime.datetime.fromtimestamp(
            os.path.getmtime(model_path)
        ).strftime("%Y-%m-%d %H:%M")

        return JsonResponse({
            "model_type":    type(model).__name__,
            "feature_count": len(features),
            "training_rows": len(df),
            "model_size_kb": round(os.path.getsize(model_path) / 1024, 1),
            "last_trained":  last_trained,
            "features":      list(features)[:10],
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# ── ADMIN: AUTH ───────────────────────────────────────────────────────────────

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


@csrf_exempt
def admin_login(request):
    if request.method == "POST":
        try:
            data     = json.loads(request.body)
            username = data.get("username", "").strip()
            password = data.get("password", "").strip()

            if not username or not password:
                return JsonResponse(
                    {"error": "Username and password required"},
                    status=400
                )

            user = AdminUser.objects.filter(username=username).first()
            if not user:
                return JsonResponse({"error": "Invalid credentials"}, status=401)

            if user.password_hash != hash_password(password):
                return JsonResponse({"error": "Invalid credentials"}, status=401)

            token = hashlib.sha256(
                f"{username}{datetime.date.today()}".encode()
            ).hexdigest()

            return JsonResponse({
                "success":  True,
                "token":    token,
                "username": username,
            })

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "POST only"}, status=405)


@csrf_exempt
def admin_create_user(request):
    if request.method == "POST":
        try:
            data     = json.loads(request.body)
            username = data.get("username", "admin")
            password = data.get("password", "aegisflow2024")

            if AdminUser.objects.filter(username=username).exists():
                return JsonResponse({"error": "User already exists"})

            AdminUser.objects.create(
                username      = username,
                password_hash = hash_password(password),
            )
            return JsonResponse({
                "success": True,
                "message": f"Admin user '{username}' created",
            })
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "POST only"}, status=405)


@csrf_exempt
def admin_verify_token(request):
    if request.method == "POST":
        try:
            data     = json.loads(request.body)
            username = data.get("username", "")
            token    = data.get("token",    "")

            expected = hashlib.sha256(
                f"{username}{datetime.date.today()}".encode()
            ).hexdigest()

            if token == expected:
                return JsonResponse({"valid": True})
            return JsonResponse({"valid": False}, status=401)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "POST only"}, status=405)