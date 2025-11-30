from flask import Flask, render_template, redirect, url_for, session, request, jsonify, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
import requests
from datetime import datetime, timedelta, timezone
import pnwkit
from config import Config
import os
import csv
import io

app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)

from models import User, Announcement, ActivityLog

DISCORD_CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
DISCORD_REDIRECT_URI = os.getenv('DISCORD_REDIRECT_URI', 'http://localhost:5000/callback')
DISCORD_API_BASE = 'https://discord.com/api/v10'

PNW_API_KEY = os.getenv('PNW_API_KEY')
ALLIANCE_ID = int(os.getenv('ALLIANCE_ID', '0'))

kit = pnwkit.QueryKit(PNW_API_KEY)

ADMIN_RANKS = ['Bushido', 'Daimyo', 'Shogun']

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def nation_linked_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if not user or not user.nation_id:
            flash('Please link your P&W nation first.', 'warning')
            return redirect(url_for('profile'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if not user or not user.nation_id:
            flash('Please link your P&W nation first.', 'warning')
            return redirect(url_for('profile'))
        if user.rank not in ADMIN_RANKS:
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login')
def login():
    discord_login_url = f"{DISCORD_API_BASE}/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={DISCORD_REDIRECT_URI}&response_type=code&scope=identify"
    return redirect(discord_login_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        flash('Login failed. Please try again.', 'danger')
        return redirect(url_for('index'))
    
    try:
        data = {
            'client_id': DISCORD_CLIENT_ID,
            'client_secret': DISCORD_CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': DISCORD_REDIRECT_URI
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        r = requests.post(f"{DISCORD_API_BASE}/oauth2/token", data=data, headers=headers)
        r.raise_for_status()
        token = r.json()
        
        headers = {'Authorization': f"Bearer {token['access_token']}"}
        r = requests.get(f"{DISCORD_API_BASE}/users/@me", headers=headers)
        discord_user = r.json()
        
        user = User.query.filter_by(discord_id=discord_user['id']).first()
        
        if not user:
            user = User(
                discord_id=discord_user['id'],
                discord_username=f"{discord_user['username']}#{discord_user.get('discriminator', '0')}"
            )
            db.session.add(user)
            db.session.commit()
            flash('Welcome! Please link your P&W nation to continue.', 'info')
        else:
            if user.nation_id:
                sync_user_rank(user)
        
        session['user_id'] = user.id
        session['discord_username'] = user.discord_username
        
        if not user.nation_id:
            return redirect(url_for('profile'))
        
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        app.logger.error(f"Login error: {e}")
        flash('Login failed. Please try again.', 'danger')
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        nation_name = request.form.get('nation_name', '').strip()
        api_key = request.form.get('api_key', '').strip()
        
        if not nation_name:
            flash('Nation name is required.', 'danger')
            return render_template('profile.html', user=user)
        
        try:
            query = kit.query("nations", {
                "nation_name": [nation_name],
                "first": 1
            }, "id nation_name alliance_id alliance_position")
            
            result = query.get()
            
            if not hasattr(result, 'nations') or not result.nations:
                flash('Nation not found in Politics & War.', 'danger')
                return render_template('profile.html', user=user)
            
            nation = result.nations[0]
            
            if nation.alliance_id != ALLIANCE_ID:
                flash(f'You are not a member of our alliance. Your alliance ID: {nation.alliance_id}, Required: {ALLIANCE_ID}', 'danger')
                return render_template('profile.html', user=user)
            
            user.nation_id = nation.id
            user.nation_name = nation.nation_name
            user.rank = nation.alliance_position if hasattr(nation, 'alliance_position') else 'Member'
            
            if api_key:
                user.set_api_key(api_key)
            
            db.session.commit()
            
            log = ActivityLog(
                user_id=user.id,
                action='Nation Linked',
                details=f'Linked nation: {nation.nation_name}'
            )
            db.session.add(log)
            db.session.commit()
            
            flash('Nation linked successfully!', 'success')
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            app.logger.error(f"Nation link error: {e}")
            flash(f'Error linking nation: {str(e)}', 'danger')
            return render_template('profile.html', user=user)
    
    return render_template('profile.html', user=user)

@app.route('/dashboard')
@nation_linked_required
def dashboard():
    user = User.query.get(session['user_id'])
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).limit(5).all()
    
    inactive_members = get_inactive_members()
    
    alliance_wars = get_alliance_wars()
    
    return render_template('dashboard.html', 
                         user=user, 
                         announcements=announcements,
                         inactive_members=inactive_members,
                         alliance_wars=alliance_wars,
                         is_admin=user.rank in ADMIN_RANKS)

@app.route('/nations')
@nation_linked_required
def nations():
    user = User.query.get(session['user_id'])
    nations_data = get_all_nations_data()
    return render_template('nations.html', user=user, nations=nations_data)

@app.route('/resources')
@nation_linked_required
def resources():
    user = User.query.get(session['user_id'])
    resource_prices = get_resource_prices()
    return render_template('resources.html', user=user, prices=resource_prices, now=datetime.utcnow())

@app.route('/api/announcement', methods=['POST'])
@admin_required
def create_announcement():
    user = User.query.get(session['user_id'])
    data = request.json
    
    announcement = Announcement(
        title=data.get('title'),
        content=data.get('content'),
        author=user.nation_name or user.discord_username
    )
    db.session.add(announcement)
    db.session.commit()
    
    log = ActivityLog(
        user_id=user.id,
        action='Announcement Created',
        details=f'Title: {announcement.title}'
    )
    db.session.add(log)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Announcement created successfully'})

@app.route('/api/announcement/<int:id>', methods=['PUT', 'DELETE'])
@admin_required
def manage_announcement(id):
    user = User.query.get(session['user_id'])
    announcement = Announcement.query.get_or_404(id)
    
    if request.method == 'DELETE':
        db.session.delete(announcement)
        db.session.commit()
        
        log = ActivityLog(
            user_id=user.id,
            action='Announcement Deleted',
            details=f'Deleted: {announcement.title}'
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Announcement deleted'})
    
    if request.method == 'PUT':
        data = request.json
        announcement.title = data.get('title', announcement.title)
        announcement.content = data.get('content', announcement.content)
        db.session.commit()
        
        log = ActivityLog(
            user_id=user.id,
            action='Announcement Updated',
            details=f'Updated: {announcement.title}'
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Announcement updated'})

@app.route('/api/send-resources', methods=['POST'])
@nation_linked_required
def send_resources():
    user = User.query.get(session['user_id'])
    
    api_key = user.get_api_key()
    if not api_key:
        return jsonify({'success': False, 'message': 'API key not set. Please update your profile.'}), 400
    
    data = request.json
    recipient_id = data.get('recipient_id')
    
    try:
        user_kit = pnwkit.QueryKit(api_key)
        
        resources = {}
        resource_fields = ['money', 'food', 'coal', 'oil', 'uranium', 'lead', 
                          'iron', 'bauxite', 'gasoline', 'munitions', 'steel', 'aluminum']
        
        for field in resource_fields:
            value = float(data.get(field, 0))
            if value > 0:
                resources[field] = value
        
        if not resources:
            return jsonify({'success': False, 'message': 'No resources specified'}), 400
        
        mutation = user_kit.mutation("bankDeposit", {
            "receiver": recipient_id,
            "note": "Sent via Lotus",
            **resources
        }, "id")
        
        result = mutation.get()
        
        log = ActivityLog(
            user_id=user.id,
            action='Resources Sent',
            details=f'To nation {recipient_id}: {resources}'
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Resources sent successfully'})
        
    except Exception as e:
        app.logger.error(f"Resource send error: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

@app.route('/api/export-nations')
@nation_linked_required
def export_nations():
    nations_data = get_all_nations_data()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['Nation Name', 'Cities', 'Beige Turns', 'Color', 'Soldiers', 
                     'Tanks', 'Aircraft', 'Ships', 'Missiles', 'Nukes', 'Last Active'])
    
    for nation in nations_data:
        writer.writerow([
            nation.nation_name,
            nation.num_cities,
            nation.beige_turns,
            nation.color,
            nation.soldiers,
            nation.tanks,
            nation.aircraft,
            nation.ships,
            nation.missiles,
            nation.nukes,
            nation.last_active
        ])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'nations_{datetime.utcnow().strftime("%Y%m%d")}.csv'
    )

@app.route('/api/export-prices')
@nation_linked_required
def export_prices():
    prices = get_resource_prices()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['Resource', 'Price (USD)'])
    
    resources = ['food', 'coal', 'oil', 'uranium', 'lead', 'iron', 'bauxite', 
                'gasoline', 'munitions', 'steel', 'aluminum']
    
    for resource in resources:
        if hasattr(prices, resource):
            writer.writerow([resource.capitalize(), getattr(prices, resource)])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'prices_{datetime.utcnow().strftime("%Y%m%d")}.csv'
    )

def sync_user_rank(user):
    try:
        query = kit.query("nations", {
            "id": user.nation_id,
            "first": 1
        }, "alliance_position")
        
        result = query.get()
        
        if hasattr(result, 'nations') and result.nations:
            nation = result.nations[0]
            if hasattr(nation, 'alliance_position'):
                user.rank = nation.alliance_position
                db.session.commit()
    except Exception as e:
        app.logger.error(f"Error syncing rank for user {user.id}: {e}")

def get_inactive_members():
    try:
        query = kit.query("nations", {
            "alliance_id": ALLIANCE_ID,
            "first": 250
        }, "nation_name last_active")
        
        result = query.get()
        inactive = []
        
        if not hasattr(result, 'nations'):
            return inactive
        
        now_utc = datetime.now(timezone.utc)
        
        for nation in result.nations:
            try:
                last_active_str = nation.last_active.replace('Z', '+00:00')
                last_active = datetime.fromisoformat(last_active_str)
                
                days_inactive = (now_utc - last_active).days
                
                if days_inactive >= 3:
                    inactive.append({
                        'name': nation.nation_name,
                        'days': days_inactive
                    })
            except Exception as e:
                app.logger.error(f"Error parsing activity for {nation.nation_name}: {e}")
                continue
        
        return sorted(inactive, key=lambda x: x['days'], reverse=True)
    except Exception as e:
        app.logger.error(f"Error getting inactive members: {e}")
        return []

def get_alliance_wars():
    try:
        query = kit.query("wars", {
            "alliance_id": ALLIANCE_ID,
            "active": True,
            "first": 100
        }, "war_type attacker{nation_name} defender{nation_name} turns_left")
        
        result = query.get()
        return result.wars if hasattr(result, 'wars') else []
    except Exception as e:
        app.logger.error(f"Error getting wars: {e}")
        return []

def get_all_nations_data():
    try:
        all_nations = []
        page = 1
        has_more = True
        
        while has_more and page <= 5:
            query = kit.query("nations", {
                "alliance_id": ALLIANCE_ID,
                "first": 250,
                "page": page
            }, """
                id nation_name num_cities beige_turns projects soldiers tanks aircraft ships 
                missiles nukes color last_active alliance_position
            """)
            
            result = query.get()
            
            if hasattr(result, 'nations') and result.nations:
                all_nations.extend(result.nations)
                has_more = len(result.nations) == 250
                page += 1
            else:
                has_more = False
        
        return all_nations
    except Exception as e:
        app.logger.error(f"Error getting nations data: {e}")
        return []

def get_resource_prices():
    try:
        query = kit.query("tradeprices", {}, """
            food coal oil uranium lead iron bauxite gasoline munitions steel aluminum
        """)
        
        result = query.get()
        return result.tradeprices[0] if hasattr(result, 'tradeprices') and result.tradeprices else None
    except Exception as e:
        app.logger.error(f"Error getting prices: {e}")
        return None

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
