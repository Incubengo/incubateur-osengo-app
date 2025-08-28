"""Main application for the Osengo Incubator appointment booking system.

This Flask application implements a lightweight booking system tailored to the
requirements described in the project specification.  It allows project
founders to select an agency, view available time slots and book a meeting
while collecting basic information about their project.  Counsellors can
manage agencies, time slots and bookings through a password‑protected back
office.  Administrators can also edit simple content pages (e.g., about,
team, news).

The application relies on open source components only:

* **Flask** for routing, views and templating.
* **SQLite** via SQLAlchemy for the data store.  SQLite is bundled with
  Python and requires no server installation.
* **Bootstrap** for responsive UI (loaded via CDN so there is no
  external dependency at deploy time).

The project can be run locally (`python app.py`) or deployed to any
platform that supports Python and Flask.  For a free deployment, consider
platforms like Render or Fly.io which offer free tiers for small
applications.  Because the site contains dynamic back‑office features it
cannot be hosted on static hosting platforms like GitHub Pages.

Usage:

    python app.py

Environment variables:

* ``SECRET_KEY`` – secret string used for session signing.  Set this to a
  long random value in production.
* ``ADMIN_PASSWORD`` – password for the back‑office.  Default is ``admin``.
* ``SMTP_SERVER`` / ``SMTP_PORT`` / ``SMTP_USERNAME`` / ``SMTP_PASSWORD`` –
  optional settings for sending real confirmation emails.  If omitted,
  confirmation emails are printed to the console.

Before running the application for the first time you should create the
database by running ``flask db init`` and ``flask db upgrade``.  See
``README.md`` for full setup instructions.
"""

import os
import uuid
import secrets
# Import timedelta in addition to datetime, date and time for slot generation
from datetime import datetime, date, time, timedelta

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    send_file,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import joinedload
import csv
import io


def create_app():
    """Factory for creating the Flask app.

    Using an application factory pattern makes it easier to configure the
    application for testing or production.  Configuration values can be
    passed via the ``FLASK_APP_SETTINGS`` environment variable.
    """
    app = Flask(__name__)
    # Generate a default secret key if one is not provided.  In production
    # this should be explicitly set via an environment variable to ensure
    # sessions are secure.
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(16))
    # Configure SQLite database.  The database file lives next to this
    # module inside the project directory.
    base_dir = os.path.abspath(os.path.dirname(__file__))
    db_path = os.path.join(base_dir, 'data.sqlite')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db = SQLAlchemy(app)

    # ----------------------------------------------------------------------
    # Database models
    # ----------------------------------------------------------------------

    class Agency(db.Model):
        """Represents an agency where appointments take place."""
        __tablename__ = 'agencies'
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(100), nullable=False)
        city = db.Column(db.String(100), nullable=True)
        description = db.Column(db.Text, nullable=True)
        slots = db.relationship('TimeSlot', backref='agency', cascade='all,delete', lazy=True)

        def __repr__(self) -> str:
            return f'<Agency {self.name}>'

    class TimeSlot(db.Model):
        """Represents an available appointment slot at a given agency."""
        __tablename__ = 'time_slots'
        id = db.Column(db.Integer, primary_key=True)
        agency_id = db.Column(db.Integer, db.ForeignKey('agencies.id'), nullable=False)
        start = db.Column(db.DateTime, nullable=False)
        end = db.Column(db.DateTime, nullable=False)
        is_booked = db.Column(db.Boolean, default=False)
        bookings = db.relationship('Booking', backref='slot', cascade='all,delete', lazy=True)

        def __repr__(self) -> str:
            return f'<TimeSlot {self.start} - {self.end}>'

    class Booking(db.Model):
        """Represents a booking made by a project founder."""
        __tablename__ = 'bookings'
        id = db.Column(db.Integer, primary_key=True)
        slot_id = db.Column(db.Integer, db.ForeignKey('time_slots.id'), nullable=False)
        name = db.Column(db.String(100), nullable=False)
        surname = db.Column(db.String(100), nullable=False)
        email = db.Column(db.String(150), nullable=False)
        phone = db.Column(db.String(30), nullable=False)
        city = db.Column(db.String(100), nullable=True)
        postal_code = db.Column(db.String(20), nullable=True)
        project_stage = db.Column(db.String(100), nullable=True)
        sector = db.Column(db.String(100), nullable=True)
        needs = db.Column(db.Text, nullable=True)

        # Additional description field for the project.  This allows users to
        # describe their project in more detail when booking a meeting.  It is
        # optional (nullable) to maintain backward‑compatibility with existing
        # records.
        description = db.Column(db.Text, nullable=True)
        status = db.Column(db.String(20), default='pending')  # pending/accepted/refused/cancelled
        cancel_token = db.Column(db.String(64), unique=True, nullable=False)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

        def __repr__(self) -> str:
            return f'<Booking {self.name} {self.surname} - {self.slot.start}>'

    class Page(db.Model):
        """Simple content pages editable by the administrator."""
        __tablename__ = 'pages'
        id = db.Column(db.Integer, primary_key=True)
        slug = db.Column(db.String(50), unique=True, nullable=False)
        title = db.Column(db.String(100), nullable=False)
        content = db.Column(db.Text, nullable=False)

        def __repr__(self) -> str:
            return f'<Page {self.slug}>'

    # Make models accessible from the app instance
    app.db = db
    app.Agency = Agency
    app.TimeSlot = TimeSlot
    app.Booking = Booking
    app.Page = Page

    # Expose datetime in Jinja templates so we can display the current year
    @app.context_processor
    def inject_now():
        from datetime import datetime as _dt  # avoid shadowing outer import
        # Also expose pages to navbar in all templates
        pages = Page.query.order_by(Page.slug).all() if 'Page' in globals() else []
        return dict(datetime=_dt, pages=pages)

    # ----------------------------------------------------------------------
    # Utility functions
    # ----------------------------------------------------------------------

    def send_confirmation_email(booking: Booking):
        """Send a confirmation email to the user.

        In production this function can be configured to use a real SMTP
        service.  If SMTP configuration variables are missing the email
        content is printed to the console instead.  The email contains
        details of the booking and a unique cancellation/reschedule link.
        """
        subject = f"Confirmation de votre rendez‑vous avec l'incubateur Osengo"
        cancel_link = url_for('cancel_booking', token=booking.cancel_token, _external=True)
        message = (f"Bonjour {booking.name} {booking.surname},\n\n"
                   f"Votre rendez‑vous est confirmé pour le {booking.slot.start.strftime('%d/%m/%Y à %H:%M')}\n"
                   f"Lieu : {booking.slot.agency.name}, {booking.slot.agency.city}\n\n"
                   f"Si vous souhaitez annuler ou reprogrammer votre rendez‑vous, cliquez sur le lien suivant : {cancel_link}\n\n"
                   f"À bientôt !\nL'équipe de l'incubateur Osengo")
        # Check for SMTP settings
        smtp_server = os.environ.get('SMTP_SERVER')
        smtp_port = int(os.environ.get('SMTP_PORT', '0'))
        smtp_user = os.environ.get('SMTP_USERNAME')
        smtp_password = os.environ.get('SMTP_PASSWORD')
        if smtp_server and smtp_port and smtp_user and smtp_password:
            import smtplib
            from email.message import EmailMessage
            msg = EmailMessage()
            msg['Subject'] = subject
            msg['From'] = smtp_user
            msg['To'] = booking.email
            msg.set_content(message)
            try:
                with smtplib.SMTP(smtp_server, smtp_port) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_password)
                    server.send_message(msg)
            except Exception as exc:
                print(f"Erreur lors de l'envoi de l'email : {exc}")
        else:
            # Fallback: print to console
            print("--- Confirmation email (simulation) ---")
            print(f"To: {booking.email}")
            print(f"Subject: {subject}\n")
            print(message)
            print("--------------------------------------")


    def require_login():
        """Helper to enforce login for back‑office routes."""
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return None

    # ----------------------------------------------------------------------
    # Routes – Public side
    # ----------------------------------------------------------------------

    @app.route('/')
    def index():
        """Homepage – allow user to select an agency or view pages."""
        agencies = Agency.query.order_by(Agency.name).all()
        pages = Page.query.all()
        return render_template('index.html', agencies=agencies, pages=pages)

    @app.route('/agency/<int:agency_id>')
    def select_agency(agency_id):
        """Show available time slots for a given agency."""
        agency = Agency.query.get_or_404(agency_id)
        # Only show future slots that are not booked
        now = datetime.now()
        slots = (TimeSlot.query
                 .filter_by(agency_id=agency_id, is_booked=False)
                 .filter(TimeSlot.start >= now)
                 .order_by(TimeSlot.start)
                 .all())
        return render_template('slots.html', agency=agency, slots=slots)

    @app.route('/book/<int:slot_id>', methods=['GET', 'POST'])
    def book(slot_id):
        """Handle display and processing of the booking form."""
        slot = TimeSlot.query.get_or_404(slot_id)
        if slot.is_booked:
            flash('Ce créneau a déjà été réservé.', 'warning')
            return redirect(url_for('select_agency', agency_id=slot.agency_id))
        if request.method == 'POST':
            # Retrieve form data
            name = request.form.get('name', '').strip()
            surname = request.form.get('surname', '').strip()
            email = request.form.get('email', '').strip()
            phone = request.form.get('phone', '').strip()
            city = request.form.get('city', '').strip()
            postal_code = request.form.get('postal_code', '').strip()
            project_stage = request.form.get('project_stage', '').strip()
            sector = request.form.get('sector', '').strip()
            description = request.form.get('description', '').strip()
            needs = request.form.get('needs', '').strip()
            if not all([name, surname, email, phone]):
                flash('Merci de renseigner au moins les champs nom, prénom, email et téléphone.', 'danger')
                return render_template('booking_form.html', slot=slot)
            # Create booking
            cancel_token = uuid.uuid4().hex
            booking = Booking(
                slot_id=slot.id,
                name=name,
                surname=surname,
                email=email,
                phone=phone,
                city=city,
                postal_code=postal_code,
                project_stage=project_stage,
                sector=sector,
                description=description,
                needs=needs,
                cancel_token=cancel_token,
                status='pending'
            )
            slot.is_booked = True
            db.session.add(booking)
            db.session.commit()
            # Send confirmation email
            send_confirmation_email(booking)
            flash("Votre rendez‑vous est enregistré. Un email de confirmation vous a été envoyé.", 'success')
            return redirect(url_for('confirmation', token=cancel_token))
        return render_template('booking_form.html', slot=slot)

    @app.route('/confirmation/<token>')
    def confirmation(token):
        """Confirmation page displayed after a successful booking."""
        booking = Booking.query.filter_by(cancel_token=token).first_or_404()
        return render_template('confirmation.html', booking=booking)

    @app.route('/cancel/<token>', methods=['GET', 'POST'])
    def cancel_booking(token):
        """Allow users to cancel or reschedule their booking."""
        booking = Booking.query.filter_by(cancel_token=token).first_or_404()
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'cancel':
                booking.status = 'cancelled'
                booking.slot.is_booked = False
                db.session.commit()
                flash('Votre rendez‑vous a été annulé.', 'info')
                return redirect(url_for('index'))
            elif action == 'reschedule':
                # Reset current slot and redirect to choose a new slot
                booking.slot.is_booked = False
                db.session.commit()
                flash('Choisissez un nouveau créneau.', 'info')
                return redirect(url_for('select_agency', agency_id=booking.slot.agency_id))
        return render_template('cancel.html', booking=booking)

    @app.route('/page/<slug>')
    def show_page(slug):
        """Render a simple content page by slug."""
        page = Page.query.filter_by(slug=slug).first_or_404()
        return render_template('page.html', page=page)

    # ----------------------------------------------------------------------
    # Routes – Authentication
    # ----------------------------------------------------------------------

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """Simple login form for back‑office access."""
        if request.method == 'POST':
            password = request.form.get('password', '')
            stored_hash = generate_password_hash(os.environ.get('ADMIN_PASSWORD', 'admin'))
            # Check password; note we generate a hash on the fly from env var
            if check_password_hash(stored_hash, password):
                session['logged_in'] = True
                flash('Connexion réussie.', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Mot de passe incorrect.', 'danger')
        return render_template('login.html')

    @app.route('/logout')
    def logout():
        session.clear()
        flash('Vous êtes déconnecté.', 'info')
        return redirect(url_for('index'))

    # ----------------------------------------------------------------------
    # Routes – Back‑office
    # ----------------------------------------------------------------------

    @app.route('/admin')
    def dashboard():
        """Back‑office dashboard overview."""
        if require_login():
            return require_login()
        # Count bookings by status
        counts = {
            'pending': Booking.query.filter_by(status='pending').count(),
            'accepted': Booking.query.filter_by(status='accepted').count(),
            'refused': Booking.query.filter_by(status='refused').count(),
            'cancelled': Booking.query.filter_by(status='cancelled').count(),
        }
        return render_template('dashboard.html', counts=counts)

    # Agencies management
    @app.route('/admin/agencies', methods=['GET', 'POST'])
    def manage_agencies():
        """List all agencies and allow creation of new ones.

        The listing displays each agency's name, city and description. A form at
        the top of the page lets administrators add a new agency. This view
        delegates editing and deletion to dedicated routes.
        """
        if require_login():
            return require_login()
        if request.method == 'POST':
            # Create a new agency from the submitted form
            name = request.form.get('name', '').strip()
            city = request.form.get('city', '').strip()
            description = request.form.get('description', '').strip()
            if name:
                agency = Agency(name=name, city=city, description=description)
                db.session.add(agency)
                db.session.commit()
                flash('Agence créée.', 'success')
        agencies = Agency.query.order_by(Agency.name).all()
        return render_template('manage_agencies.html', agencies=agencies)

    @app.route('/admin/agencies/<int:agency_id>/edit', methods=['GET', 'POST'])
    def edit_agency(agency_id):
        """Edit an existing agency.

        Displays a form pre‑populated with the agency's current values. On
        submission, the agency is updated and the user is redirected back to
        the agencies list.
        """
        if require_login():
            return require_login()
        agency = Agency.query.get_or_404(agency_id)
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            city = request.form.get('city', '').strip()
            description = request.form.get('description', '').strip()
            if name:
                agency.name = name
                agency.city = city
                agency.description = description
                db.session.commit()
                flash('Agence modifiée.', 'success')
                return redirect(url_for('manage_agencies'))
        return render_template('edit_agency.html', agency=agency)

    @app.route('/admin/agencies/<int:agency_id>/delete', methods=['POST'])
    def delete_agency(agency_id):
        if require_login():
            return require_login()
        agency = Agency.query.get_or_404(agency_id)
        db.session.delete(agency)
        db.session.commit()
        flash('Agence supprimée.', 'info')
        return redirect(url_for('manage_agencies'))

    # Time slots management
    @app.route('/admin/slots', methods=['GET', 'POST'])
    def manage_slots():
        if require_login():
            return require_login()
        agencies = Agency.query.order_by(Agency.name).all()
        # Adding new slot
        if request.method == 'POST':
            agency_id = int(request.form.get('agency_id'))
            date_str = request.form.get('date')
            start_time = request.form.get('start_time')
            end_time = request.form.get('end_time')
            if date_str and start_time and end_time:
                # Parse the provided start and end times into datetime objects.  These
                # represent a continuous range of availability provided by the
                # conseiller.  We will subdivide this range into one‑hour slots.
                start_dt = datetime.strptime(f"{date_str} {start_time}", "%Y-%m-%d %H:%M")
                end_dt = datetime.strptime(f"{date_str} {end_time}", "%Y-%m-%d %H:%M")
                if end_dt <= start_dt:
                    flash('L’heure de fin doit être après l’heure de début.', 'danger')
                else:
                    # Generate 1‑hour increments between start_dt and end_dt.  The
                    # last slot will end exactly at end_dt; any remainder less than
                    # an hour is ignored.  Each slot is saved to the database.
                    current = start_dt
                    created_count = 0
                    while current + timedelta(hours=1) <= end_dt:
                        next_end = current + timedelta(hours=1)
                        slot = TimeSlot(agency_id=agency_id, start=current, end=next_end)
                        db.session.add(slot)
                        created_count += 1
                        current = next_end
                    db.session.commit()
                    if created_count == 1:
                        flash('Créneau ajouté.', 'success')
                    else:
                        flash(f'{created_count} créneaux ajoutés.', 'success')
        # Query all slots for listing (including booked) to allow deletion
        slots = TimeSlot.query.options(joinedload(TimeSlot.agency)).order_by(TimeSlot.start.desc()).all()
        return render_template('manage_slots.html', agencies=agencies, slots=slots)

    @app.route('/admin/slots/<int:slot_id>/delete', methods=['POST'])
    def delete_slot(slot_id):
        if require_login():
            return require_login()
        slot = TimeSlot.query.get_or_404(slot_id)
        db.session.delete(slot)
        db.session.commit()
        flash('Créneau supprimé.', 'info')
        return redirect(url_for('manage_slots'))

    # Bookings management
    @app.route('/admin/bookings', methods=['GET', 'POST'])
    def manage_bookings():
        if require_login():
            return require_login()
        # Accept/refuse bookings
        if request.method == 'POST':
            booking_id = int(request.form.get('booking_id'))
            action = request.form.get('action')
            booking = Booking.query.get_or_404(booking_id)
            if action == 'accept':
                booking.status = 'accepted'
                flash('Rendez‑vous accepté.', 'success')
            elif action == 'refuse':
                booking.status = 'refused'
                booking.slot.is_booked = False
                flash('Rendez‑vous refusé.', 'info')
            db.session.commit()
        bookings = (Booking.query.options(joinedload(Booking.slot).joinedload(TimeSlot.agency))
                    .order_by(Booking.created_at.desc()).all())
        return render_template('manage_bookings.html', bookings=bookings)

    @app.route('/admin/export')
    def export_bookings():
        if require_login():
            return require_login()
        # Export bookings and questionnaire answers to CSV
        bookings = Booking.query.options(joinedload(Booking.slot).joinedload(TimeSlot.agency)).all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'ID', 'Agence', 'Début', 'Fin', 'Nom', 'Prénom', 'Email', 'Téléphone',
            'Ville', 'Code postal', 'Stade du projet', 'Secteur', 'Description', 'Besoins',
            'Statut', 'Date de création'
        ])
        for b in bookings:
            writer.writerow([
                b.id,
                b.slot.agency.name,
                b.slot.start.strftime('%Y-%m-%d %H:%M'),
                b.slot.end.strftime('%Y-%m-%d %H:%M'),
                b.name,
                b.surname,
                b.email,
                b.phone,
                b.city,
                b.postal_code,
                b.project_stage,
                b.sector,
                b.description,
                b.needs,
                b.status,
                b.created_at.strftime('%Y-%m-%d %H:%M'),
            ])
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name='bookings.csv'
        )

    # Content page management
    @app.route('/admin/pages', methods=['GET', 'POST'])
    def manage_pages():
        if require_login():
            return require_login()
        page_to_edit = None
        # Handle edit query parameter
        edit_id = request.args.get('edit')
        if edit_id:
            page_to_edit = Page.query.get_or_404(int(edit_id))
        if request.method == 'POST':
            slug = request.form.get('slug', '').strip()
            title = request.form.get('title', '').strip()
            content = request.form.get('content', '').strip()
            page_id = request.form.get('page_id')
            if page_id:
                # Update existing page
                page = Page.query.get_or_404(int(page_id))
                page.slug = slug
                page.title = title
                page.content = content
                flash('Page mise à jour.', 'success')
            else:
                # Create new page
                if slug and title and content:
                    page = Page(slug=slug, title=title, content=content)
                    db.session.add(page)
                    flash('Page créée.', 'success')
            db.session.commit()
            return redirect(url_for('manage_pages'))
        pages = Page.query.order_by(Page.slug).all()
        return render_template('manage_pages.html', pages=pages, page_to_edit=page_to_edit)

    @app.route('/admin/pages/<int:page_id>/delete', methods=['POST'])
    def delete_page(page_id):
        if require_login():
            return require_login()
        page = Page.query.get_or_404(page_id)
        db.session.delete(page)
        db.session.commit()
        flash('Page supprimée.', 'info')
        return redirect(url_for('manage_pages'))

    # ----------------------------------------------------------------------
    # CLI command to initialize the database
    # ----------------------------------------------------------------------
    @app.cli.command('init-db')
    def init_db():
        """Create all database tables and insert sample data."""
        db.create_all()
        # Insert sample agencies if none exist
        if Agency.query.count() == 0:
            sample = [
                Agency(name='Clermont‑Ferrand', city='Clermont‑Ferrand', description='Agence de Clermont'),
                Agency(name='Lyon', city='Lyon', description='Agence de Lyon'),
                Agency(name='Grenoble', city='Grenoble', description='Agence de Grenoble'),
            ]
            db.session.bulk_save_objects(sample)
            db.session.commit()
            print('Inserted sample agencies.')
        else:
            print('Agencies already exist.')
        # Insert default pages
        if Page.query.count() == 0:
            pages = [
                Page(slug='a-propos', title='À propos de l’incubateur',
                     content='Cette page présente l’incubateur et sa mission.'),
                Page(slug='equipe', title='Notre équipe',
                     content='Présentation des membres de l’équipe de l’incubateur.'),
                Page(slug='actualites', title='Actualités',
                     content='Retrouvez ici les dernières actualités de l’incubateur.'),
            ]
            db.session.bulk_save_objects(pages)
            db.session.commit()
            print('Inserted sample pages.')
        else:
            print('Pages already exist.')

    return app


if __name__ == '__main__':
    # Create and run the app
    application = create_app()
    application.run(debug=True)