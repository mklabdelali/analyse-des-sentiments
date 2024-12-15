from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
#api analyse des entiments
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from pymongo import MongoClient
from datetime import datetime, timedelta
from textblob import TextBlob
from bson.objectid import ObjectId
from bson.json_util import dumps
import random
#Nlp AraBERT
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
from arabic_reshaper import reshape
from bidi.algorithm import get_display
#translate
from deep_translator import GoogleTranslator

app = Flask(__name__)
app.secret_key = "votre_cle_secrete"

# Configuration de Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# Connexion MongoDB
client = MongoClient("mongodb://localhost:27017/")
db = client["db_sentiment"]
users_collection = db["users"]
comments_collection = db["comments"]
services_collection = db["services"]

analyzer = SentimentIntensityAnalyzer()


#route enregistrement
@app.route("/admin/patients")
#@login_required
#@admin_required
def patients():
    return render_template("patients.html")

#route enregistrement commentaire
@app.route("/save_comment", methods=["POST"])
def save_comment():

    if "username" not in session:
        flash("Vous devez être connecté pour poster un commentaire.", "danger")
        return redirect(url_for("login"))

    if request.method == "POST":
        username = request.form.get("username")
        comment = request.form.get("comment")
        language = request.form.get("language", "français")
        service = request.form.get("service")
        date_posted = datetime.utcnow()
        

        if not username or not comment:
            print("Champs obligatoires manquants.")
            flash("Tous les champs sont obligatoires.", "danger")
            return redirect(url_for("save_comment"))


        if username and comment:
            new_comment = {
                "username": username,
                "comment": comment,
                "service": service,
                "language": language,
                "date_posted": date_posted,
                "sentiment": {
                    "label": "",  
                    "polarity": 0,  
                    "subjectivity": 0  
                }
            }
            try:
                result = comments_collection.insert_one(new_comment)
                print("Insertion réussie :", result.inserted_id)
            except Exception as e:
                print("Erreur lors de l'insertion :", str(e))
                flash("Une erreur est survenue lors de l'enregistrement.", "danger")
        else:
            flash("Tous les champs sont obligatoires.", "danger")
            print("Commentaire non enregistré : champs manquants.")

    return redirect(url_for('user_comments'))


#Route login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        print(f"Essai de connexion avec username={username}")

        # Recherche de l'utilisateur dans MongoDB
        user = users_collection.find_one({"username": username})
        if user and check_password_hash(user["password"], password):
            session["username"] = username
            session["role"] = user["role"]
            print(f"Après connexion: session = {session}")
            flash("Connexion réussie !", "success")
            if session.get("role") == "admin":
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('comment_register'))
        else:
            flash("Nom d'utilisateur ou mot de passe incorrect.", "danger")
    
    return render_template('login.html')



#test si utilisateur est toujours connécter
@app.route("/check_session")
def check_session():
    if "username" in session:
        return f"Utilisateur connecté : {session['username']} avec rôle {session.get('role')}"
    return "Aucun utilisateur connecté"

#route déconnecter
@app.route("/logout")
def logout():
    print("Route /logout appelée.")  # Ajoutez ce log
    logout_user()
    session.clear()
    flash("Déconnexion réussie.", "info")
    return redirect(url_for("login"))

from datetime import datetime, timedelta

@app.route('/admin/dashboard')
def admin_dashboard():
    if "username" not in session or session.get("role") != "admin":
        flash("Accès refusé. Vous devez être administrateur.", "danger")
        return redirect(url_for('login'))

    # Paramètres de pagination
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 5))

    # Récupération des services disponibles depuis la collection `services`
    specialite = list(services_collection.find({}, {"nom": 1, "_id": 0}))
    services = sorted([service["nom"] for service in specialite])

    # Paramètres de filtrage
    service_filter = request.args.get("service", None)
    gender_filter = request.args.get("gender", None)
    selected_date = request.args.get("date_posted", None)  # Format : YYYY-MM-DD

    # Si aucune date n'est fournie, utiliser la date d'aujourd'hui
    if not selected_date:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        selected_date = today

    # Construire la requête de filtrage des commentaires
    comments_query = {}
    if service_filter:
        comments_query["service"] = service_filter
    if selected_date:
        try:
            # Convertir la date sélectionnée en datetime
            selected_date_dt = datetime.strptime(selected_date, "%Y-%m-%d")
            print(f"Date sélectionnée : {selected_date_dt}")

            # Ajouter la plage de dates au filtre
            comments_query["date_posted"] = {
                "$gte": selected_date_dt,
                "$lt": selected_date_dt + timedelta(days=1)
            }
        except ValueError:
            flash("Format de date invalide. Utilisez le format YYYY-MM-DD.", "danger")

    # Récupérer les commentaires filtrés
    filtered_comments = list(comments_collection.find(comments_query).sort("date_posted", -1))

    # Obtenir les usernames des patients associés aux commentaires filtrés
    filtered_usernames = {comment["username"] for comment in filtered_comments}

    # Construire la requête utilisateur en fonction des filtres
    users_query = {"role": "patient"}
    if gender_filter:
        users_query["gender"] = gender_filter
    if filtered_usernames:
        users_query["username"] = {"$in": list(filtered_usernames)}

    # Récupérer les patients avec pagination
    total_patients = users_collection.count_documents(users_query)
    patients_cursor = users_collection.find(users_query).skip((page - 1) * per_page).limit(per_page)
    patients = list(patients_cursor)

    # Ajouter les commentaires correspondants à chaque patient
    for patient in patients:
        patient_comments = [
            comment for comment in filtered_comments if comment["username"] == patient["username"]
        ]
        patient["_id"] = str(patient["_id"])
        patient["comments"] = patient_comments

    return render_template(
        'admin/admin_dashboard.html',
        patients=patients,
        page=page,
        per_page=per_page,
        total_patients=total_patients,
        services=services,
        service_filter=service_filter,
        gender_filter=gender_filter,
        selected_date=selected_date  # Inclure la date sélectionnée pour l'affichage dans le formulaire
    )




#liste des commentaire par patient
@app.route("/user/comments", methods=["GET"])
def user_comments():
    # Récupérer l'utilisateur connecté
    username = session.get("username")
    
    if not username:
        flash("Vous devez être connecté pour voir vos commentaires.", "danger")
        return redirect(url_for("login"))
    
    # Récupérer les commentaires de l'utilisateur
    user_comments = list(comments_collection.find({"username": username}))
    
    # Convertir les ObjectId et dates en formats lisibles
    for comment in user_comments:
        comment["_id"] = str(comment["_id"])  # Convertir ObjectId en string
        if "date_posted" in comment:
            comment["date_posted"] = comment["date_posted"].strftime("%d/%m/%Y %H:%M")

    # Envoyer les commentaires au template
    return render_template("user_comments.html", comments=user_comments)




#restriction par role
def admin_required(func):
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.role != "admin":
            flash("Vous n'avez pas les droits nécessaires pour accéder à cette page.", "danger")
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper
#routage delete user
@app.route('/admin/delete_user/<username>', methods=['POST', 'GET'])
def delete_user(username):
    if "username" not in session or session.get("role") != "admin":
        flash("Accès refusé. Vous devez être administrateur.", "danger")
        return redirect(url_for('login'))

    # Suppression de l'utilisateur dans MongoDB
    users_collection.delete_one({"username": username})
    flash(f"L'utilisateur {username} a été supprimé.", "success")
    return redirect(url_for('admin_dashboard'))

# Route pour la page send comment
@app.route('/comment', methods=["GET"])
def comment_register():

    specialites = list(services_collection.find({}))
    if specialites:
        # Choisir une spécialité au hasard
        specialite_choisie = random.choice(specialites)
        specialite_nom = specialite_choisie['nom']

    return render_template('comment_register.html',service=specialite_nom)

# Route pour la page d'accueil
@app.route('/')
def home():
    return render_template('login.html')  # Assurez-vous que "login.html" est dans le dossier "templates"


# suppression la mise en cache
@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response



# Fonction pour analyser le sentiment
@app.route('/analyze_all_sentiments', methods=['POST'])
def analyze_all_sentiments():
    try:
        data = request.json
        comments = data.get("comments", [])
        if not comments:
            return jsonify({"success": False, "message": "Aucun commentaire fourni."}), 400
        print(comments)
        results = []
        for comment_data in comments:
            patient_id = comment_data.get("patientId")
            comment_text = comment_data.get("commentText")
            language = comment_data.get("language")

            if not all([patient_id, comment_text,language]):
                continue

            if language=="arabe":
                sentiment=analyze_sentiment_ar(comment_text)
            elif language=="français":
                # Traduction de texte
                comment_text = GoogleTranslator(source='fr', target='en').translate(comment_text)
                # Analyse du sentiment
                blob = TextBlob(comment_text)
                sentiment = {
                    "label": "positif" if blob.sentiment.polarity > 0 else "négatif" if blob.sentiment.polarity < 0 else "neutre",
                    "polarity": round(blob.sentiment.polarity, 2),
                    "subjectivity": round(blob.sentiment.subjectivity, 2),
                }
            else:
                 # Analyse du sentiment
                blob = TextBlob(comment_text)
                sentiment = {
                    "label": "positif" if blob.sentiment.polarity > 0 else "négatif" if blob.sentiment.polarity < 0 else "neutre",
                    "polarity": round(blob.sentiment.polarity, 2),
                    "subjectivity": round(blob.sentiment.subjectivity, 2),
                }
                
            # Mise à jour de la base de données
            result = comments_collection.update_one(
                {"_id": ObjectId(patient_id)}, 
                {"$set": {"sentiment": sentiment}}
            )

            print(f"Patient {patient_id} : {result.matched_count} matched, {result.modified_count} modified")
            
            if result.matched_count > 0:
                results.append({"patientId": patient_id, "sentiment": sentiment})

        return jsonify({"success": True, "data": results})
       
    except Exception as e:
        print("Erreur :", str(e))
        return jsonify({"success": False, "message": str(e)}), 500
    

# Fonction pour analyser le sentiment avec un résultat structuré
def analyze_sentiment_ar(text):
    # Charger AraBERT pré-entraîné pour l'analyse des sentiments
    model_name = "aubmindlab/bert-base-arabertv2"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name)
    
    # Prétraitement du texte
    reshaped_text = reshape(text)
    bidi_text = get_display(reshaped_text)
    inputs = tokenizer(bidi_text, return_tensors="pt", truncation=True, padding=True, max_length=128)

    # Prédictions
    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits
        probabilities = torch.nn.functional.softmax(logits, dim=-1)

    # Analyse des résultats
    labels = ["négatif", "positif"]  # Ajustez si c'est binaire
    predicted_class = torch.argmax(probabilities).item()
    polarity_score = probabilities[0, 1].item() - probabilities[0, 0].item()  # Positif - Négatif

    sentiment = {
        "label": labels[predicted_class],
        "polarity": round(polarity_score, 2),
        "subjectivity": round(abs(polarity_score), 2),  # Approximation de la subjectivité
    }
    return sentiment


@app.route('/statistics', methods=['GET'])
def statistics():
    # Collections MongoDB
    users_collection = db['users']
    comments_collection = db['comments']

    # Diagramme 1 : Âge et Sentiment
    age_sentiment_data = list(comments_collection.aggregate([
        {"$lookup": {"from": "users", "localField": "username", "foreignField": "username", "as": "user"}},
        {"$unwind": "$user"},
        {"$group": {"_id": {"age": "$user.age", "sentiment": "$sentiment.label"}, "count": {"$sum": 1}}},
        {"$project": {"age": "$_id.age", "sentiment": "$_id.sentiment", "count": 1, "_id": 0}}
    ]))

    # Diagramme 2 : Sentiment par Service
    sentiment_service_data = list(comments_collection.aggregate([
        {"$group": {"_id": {"service": "$service", "sentiment": "$sentiment.label"}, "count": {"$sum": 1}}},
        {"$project": {"service": "$_id.service", "sentiment": "$_id.sentiment", "count": 1, "_id": 0}}
    ]))

    # Diagramme 3 : Sentiment par Service, Langage et Âge
    sentiment_service_language_age_data = list(comments_collection.aggregate([
        {"$lookup": {"from": "users", "localField": "username", "foreignField": "username", "as": "user"}},
        {"$unwind": "$user"},
        {"$group": {"_id": {"service": "$service", "language": "$language", "age": "$user.age", "sentiment": "$sentiment.label"}, "count": {"$sum": 1}}},
        {"$project": {"service": "$_id.service", "language": "$_id.language", "age": "$_id.age", "sentiment": "$_id.sentiment", "count": 1, "_id": 0}}
    ]))

    return jsonify({
        "age_sentiment_data": age_sentiment_data,
        "sentiment_service_data": sentiment_service_data,
        "sentiment_service_language_age_data": sentiment_service_language_age_data
    })



#route page statistique
@app.route('/admin/statistics_page', methods=['GET'])
def statistics_page():
    return render_template('admin/statistics.html')

#RDV
@app.route('/admin/rdv')
def rdv():
    return render_template('admin/rdv.html')

# Route pour ajouter un patient
from werkzeug.security import generate_password_hash

@app.route('/add_patient', methods=['POST'])
def add_patient():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    age = data.get("age")
    first_name = data.get("first_name")
    last_name = data.get("last_name")
    gender = data.get("gender")
    role = data.get("role", "patient")

    # Vérification si le nom d'utilisateur existe déjà
    if users_collection.find_one({"username": username}):
        return jsonify({"success": False, "message": "Nom d'utilisateur déjà pris."}), 400

    # Hachage du mot de passe
    hashed_password = generate_password_hash(password)

    # Préparation du document utilisateur
    user_data = {
        "username": username,
        "password": hashed_password,
        "age": age,
        "first_name": first_name,
        "last_name": last_name,
        "gender": gender,
        "role": role,
    }

    # Insérer l'utilisateur dans la base de données
    users_collection.insert_one(user_data)
    return jsonify({"success": True, "message": "Patient ajouté avec succès."}), 201


# Route pour récupérer tous les patients
@app.route("/get_patients", methods=["GET"])
def get_patients():
    try:
        # Recherche des patients ayant le rôle "patient"
        patients = list(users_collection.find({"role": "patient"}))
        return dumps({"success": True, "data": patients}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# Définir un filtre pour le formatage des dates
@app.template_filter("format_date")
def format_date(value, format="%d/%m/%Y %H:%M"):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value  # Retourne la valeur brute si elle n'est pas au bon format
    return value.strftime(format)

#class user
class User(UserMixin):
    def __init__(self, username, role):
        self.id = username
        self.role = role

@login_manager.user_loader
def load_user(username):
    user_data = users_collection.find_one({"username": username})
    if user_data:
        return User(username=user_data["username"], role=user_data["role"])
    return None


if __name__ == '__main__':
    app.run(debug=True)
