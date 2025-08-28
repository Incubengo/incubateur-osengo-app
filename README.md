# Application de prise de rendez‑vous pour l’incubateur Osengo

Ce dépôt contient un prototype de site web permettant aux porteurs de projet de
réserver un rendez‑vous avec un conseiller de l’incubateur Osengo.  Le cahier
des charges fourni par l’utilisateur a été respecté au mieux avec des
technologies libres et gratuites.  Le back‑office permet de gérer les agences,
les créneaux horaires, les rendez‑vous et le contenu des pages vitrines.

## Fonctionnalités principales

### Côté usager

* **Choix de l’agence** : liste des agences (V1 : trois villes principales
  d’Auvergne) avec description, ville et bouton pour consulter les créneaux
  disponibles.
* **Prise de rendez‑vous** : affichage des créneaux disponibles pour
  l’agence sélectionnée, formulaire de réservation collectant l’identité,
  les coordonnées, la localisation et quelques informations sur le projet.
  Une confirmation est affichée après validation et un email (simulé)
  contenant un lien pour annuler ou reprogrammer le rendez‑vous est envoyé.
* **Annulation/Reprogrammation** : via le lien reçu dans l’email, l’usager
  peut annuler ou choisir un nouveau créneau.
* **Pages de contenu** : pages « À propos », « Équipe », « Actualités », etc.

### Côté conseiller / back‑office

* **Authentification** : accès protégé par mot de passe unique (défini via
  la variable d’environnement `ADMIN_PASSWORD`).
* **Gestion des agences** : création, modification et suppression des
  agences.
* **Gestion des créneaux** : ajout de créneaux (date, heure de début,
  heure de fin) par agence, suppression de créneaux.
* **Consultation des rendez‑vous** : tableau listant tous les rendez‑vous
  avec possibilité d’accepter ou de refuser (et libérer le créneau).  Les
  rendez‑vous annulés sont indiqués.
* **Export des données** : export des rendez‑vous et des réponses aux
  questionnaires au format CSV.
* **Gestion des pages de contenu** : création, modification et suppression
  de pages vitrines.

## Architecture technique

* **Framework :** l’application est développée avec [Flask](https://flask.palletsprojects.com/), un micro‑framework Python open source.  Le code
  est volontairement simple et ne dépend pas d’autres bibliothèques
  commerciales.  Les modèles sont gérés avec SQLAlchemy et la base de
  données est un fichier SQLite (fourni par défaut avec Python).  Grâce à
  l’abstraction ORM, il est possible de migrer facilement vers une base
  externe (PostgreSQL, MySQL…).
* **Interface** : le rendu HTML est assuré par les templates Jinja2 et
  l’interface est stylisée avec [Bootstrap 5](https://getbootstrap.com/) via CDN pour garantir une bonne
  réactivité sur ordinateur, tablette et mobile.
* **Emails** : une fonction `send_confirmation_email` envoie un email de
  confirmation.  Si des variables `SMTP_SERVER`, `SMTP_PORT`,
  `SMTP_USERNAME` et `SMTP_PASSWORD` sont définies, Flask enverra un
  véritable mail via SMTP (SendGrid Free, Gmail, etc.).  Sinon, le contenu
  de l’email est affiché dans la console pour test.
* **Pages vitrines** : les pages sont stockées dans la base de données avec un
  slug, un titre et un contenu HTML/Markdown.  Elles peuvent être
  modifiées depuis le back‑office.

## Installation locale

1. **Prérequis :** installez Python 3.10 ou plus récent.  Installez les
   dépendances avec pip :

   ```bash
   pip install flask flask_sqlalchemy werkzeug
   ```

2. **Initialisation de la base** : depuis le dossier `incubateur_osengo_app`,
   exécutez :

   ```bash
   flask --app app.py init-db
   ```

   Cela créera le fichier `data.sqlite` et insérera des exemples
   d’agences et de pages.

3. **Lancement du serveur** :

   ```bash
   flask --app app.py run
   ```

4. Ouvrez votre navigateur sur `http://127.0.0.1:5000` pour accéder au site.
   Le back‑office est disponible via le lien « Connexion » dans la barre
   supérieure (mot de passe par défaut : `admin`).  Définissez les variables
   d’environnement `SECRET_KEY` et `ADMIN_PASSWORD` pour renforcer la sécurité.

## Déploiement gratuit

L’application nécessite un serveur capable d’exécuter du code Python.  Les
hébergeurs de pages statiques comme GitHub Pages ou Netlify ne conviennent
pas pour ce type d’application.  Voici quelques pistes gratuites pour
héberger le service :

* **Render.com** : offre un plan gratuit pour des services web.  Vous
  connectez votre dépôt GitHub et Render se charge de déployer l’application
  automatiquement.  Voir [la documentation Render](https://render.com/docs)
  pour plus d’informations.
* **Fly.io** ou **Railway** : proposent également des offres gratuites
  limitées qui suffisent pour un petit service.  L’installation est
  légèrement plus technique mais bien documentée.
* **PyPI / Heroku** : Heroku n’offre plus de plan gratuit illimité, mais
  propose des quotas mensuels pour les projets open source.

Pour rester fidèle à l’esprit « no‑code/low‑code », il est également
possible de remplacer la couche back‑end par un service de base de données
en ligne (Airtable, Baserow) et d’utiliser un outil comme [Tally](https://tally.so)
ou [Typeform](https://www.typeform.com/) pour créer le formulaire de prise de
rendez‑vous.  Les réponses pourraient ensuite être connectées à un agenda
(Google Agenda ou Outlook) via [Zapier](https://zapier.com/) ou [Make](https://www.make.com/) sans écrire
de code.  Le présent projet fournit néanmoins un exemple d’implémentation
complète et libre.

## Inspirations open source

* Le projet [LibreBooking](https://librebooking.readthedocs.io/en/latest/) est
  un logiciel open source de réservation de ressources.  Il met à
  disposition une interface mobile et extensible pour gérer des réservations
  et inclut des fonctionnalités avancées comme la gestion des quotas, des
  listes d’attente, un contrôle d’accès basé sur les rôles et l’intégration
  avec Outlook/Thunderbird via iCal【125718710404969†L85-L116】.  LibreBooking est une
  évolution du projet Booked Scheduler (dernière version open source en
  2020)【125718710404969†L85-L96】.
* Un autre exemple minimaliste est un système de réservation de salles
  développé avec Flask et SQLite disponible sur GitHub【376844978874465†L251-L303】.  Il
  démontre comment utiliser Flask pour gérer des ressources et authentifier
  un administrateur.

## Limitations et pistes d’évolution

* L’application prototype ne synchronise pas encore les rendez‑vous avec
  Google Agenda ou Outlook.  Une intégration iCal permettrait pourtant
  d’importer automatiquement les réservations dans les calendriers des
  conseillers.
* L’envoi d’emails est simulé par défaut.  Pour activer l’envoi réel,
  configurez les variables `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME` et
  `SMTP_PASSWORD` selon votre fournisseur (par exemple Gmail ou SendGrid).
* Les conseillers partagent pour l’instant un compte unique.  Il serait
  possible de créer des comptes individuels, des rôles et des statistiques
  (taux de rendez‑vous honorés, nombre de porteurs par agence…).
* L’interface d’édition des pages est volontairement simple.  Pour un site
  vitrine plus élaboré, on pourrait utiliser un CMS léger ou un outil
  no‑code.

Nous espérons que ce prototype vous servira de base pour mettre en place
votre service de prise de rendez‑vous en ligne !