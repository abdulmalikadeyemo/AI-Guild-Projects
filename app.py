import streamlit as st
import sqlite3
from datetime import datetime
import re
from typing import List, Dict
import pandas as pd
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os
import hashlib
import json
import time

# Constants
PROJECT_STATUSES = {
    "Idea": {
        "color": "#FFA500",  # Orange
        "description": "Initial concept stage. The project is still being conceptualized and requirements are being gathered."
    },
    "MVP": {
        "color": "#4169E1",  # Royal Blue
        "description": "Minimum Viable Product stage. A basic working prototype is being developed or already exists."
    },
    "Launch": {
        "color": "#32CD32",  # Lime Green
        "description": "Project is live and being used by end-users."
    }
}

# Authentication credentials (hardcoded for demo - in production, use environment variables)
# Get admin credentials from secrets
ADMIN_USERNAME = st.secrets["admin_credentials"]["username"]
ADMIN_PASSWORD = st.secrets["admin_credentials"]["password"]  # Store the hashed password in secrets

# Google Sheets setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = '1zsObh657CzgZgxMhS9qR9Psm64VP9tnu6I1mqzMm2ZI'
RANGE_NAME = 'Projects!A2:I'  # Updated range to include status column

def check_password():
    """Returns `True` if the user had the correct password."""
    
    # Initialize session state
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True

    # Show input fields for username and password
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    if st.button("Login"):
        if username.lower() == ADMIN_USERNAME and \
           hashlib.sha256(password.encode()).hexdigest() == ADMIN_PASSWORD:
            st.session_state.password_correct = True
            return True
        else:
            st.error("😕 User not known or password incorrect")
            return False
            
    return False

def init_google_sheets():
    """Initialize Google Sheets connection"""
    try:
        credentials = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=SCOPES
        )
        service = build('sheets', 'v4', credentials=credentials)
        return service
    except Exception as e:
        st.error(f"Error connecting to Google Sheets: {str(e)}")
        return None

# def sync_to_sheets(project_data: Dict, is_update: bool = False):
#     """Sync project data to Google Sheets"""
#     try:
#         service = init_google_sheets()
#         if not service:
#             return False, "Failed to connect to Google Sheets"

#         # Prepare data for Google Sheets
#         values = [[
#             project_data['project_name'],
#             project_data['one_liner'],
#             project_data['description'],
#             project_data['ai_usage'],
#             project_data['lead_name'],
#             project_data['whatsapp_contact'],
#             project_data['status'],
#             datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
#             "Updated" if is_update else "New Entry"
#         ]]

#         body = {
#             'values': values
#         }

#         # Append data to Google Sheet
#         result = service.spreadsheets().values().append(
#             spreadsheetId=SPREADSHEET_ID,
#             range=RANGE_NAME,
#             valueInputOption='RAW',
#             insertDataOption='INSERT_ROWS',
#             body=body
#         ).execute()

#         return True, "Successfully synced to Google Sheets"
#     except Exception as e:
#         return False, f"Error syncing to Google Sheets: {str(e)}"

def delete_project(project_name: str) -> tuple:
    """Delete project from database and Google Sheets"""
    try:
        # Delete from SQLite
        conn = sqlite3.connect('ai_projects.db')
        c = conn.cursor()
        c.execute('DELETE FROM projects WHERE project_name = ?', (project_name,))
        conn.commit()
        conn.close()

        # Delete from Google Sheets
        service = init_google_sheets()
        if not service:
            return False, "Project deleted from database but failed to connect to Google Sheets"

        row_number = find_row_in_sheets(service, project_name)
        if row_number:
            # Clear the row in Google Sheets
            range_name = f'Projects!A{row_number}:I{row_number}'
            service.spreadsheets().values().clear(
                spreadsheetId=SPREADSHEET_ID,
                range=range_name
            ).execute()

            return True, "Project successfully deleted from database and Google Sheets"
        else:
            return True, "Project deleted from database"

    except Exception as e:
        return False, f"Error deleting project: {str(e)}"

def find_row_in_sheets(service, project_name):
    """Find the row number for a project in Google Sheets"""
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=RANGE_NAME
        ).execute()
        
        rows = result.get('values', [])
        for idx, row in enumerate(rows):
            if row[0] == project_name:  # First column is project name
                return idx + 2  # +2 because range starts at A2
        return None
    except Exception as e:
        print(f"Error finding row: {str(e)}")
        return None

def sync_to_sheets(project_data: Dict, is_update: bool = False):
    """Sync project data to Google Sheets"""
    try:
        service = init_google_sheets()
        if not service:
            return False, "Failed to connect to Google Sheets"

        # Prepare data row
        values = [[
            project_data['project_name'],
            project_data['one_liner'],
            project_data['description'],
            project_data['ai_usage'],
            project_data['lead_name'],
            project_data['whatsapp_contact'],
            project_data['status'],
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "Updated" if is_update else "New Entry"
        ]]

        if is_update:
            # Find existing row
            row_number = find_row_in_sheets(service, project_data['project_name'])
            if row_number:
                # Update existing row
                range_name = f'Projects!A{row_number}:I{row_number}'
                body = {
                    'values': values
                }
                service.spreadsheets().values().update(
                    spreadsheetId=SPREADSHEET_ID,
                    range=range_name,
                    valueInputOption='RAW',
                    body=body
                ).execute()
                return True, "Successfully updated in Google Sheets"
            else:
                return False, "Project not found in Google Sheets"
        else:
            # Append new row
            body = {
                'values': values
            }
            service.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID,
                range=RANGE_NAME,
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body=body
            ).execute()
            return True, "Successfully added to Google Sheets"
            
    except Exception as e:
        return False, f"Error syncing to Google Sheets: {str(e)}"



# Database setup
def init_db():
    conn = sqlite3.connect('ai_projects.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT UNIQUE NOT NULL,
            one_liner TEXT NOT NULL,
            description TEXT NOT NULL,
            ai_usage TEXT NOT NULL,
            lead_name TEXT NOT NULL,
            whatsapp_contact TEXT NOT NULL,
            status TEXT NOT NULL,
            date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

    # Add sample project if database is empty
    conn = sqlite3.connect('ai_projects.db')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM projects')
    count = c.fetchone()[0]
    if count == 0:
        c.execute('''
            INSERT INTO projects (
                project_name, one_liner, description, ai_usage, 
                lead_name, whatsapp_contact, status
            ) VALUES (
                'Sample Project',
                'This is a sample project',
                'This is a sample description',
                'This project uses AI for demonstration',
                'Admin',
                '+1234567890',
                'Idea'
            )
        ''')
        conn.commit()
    conn.close()

# [Previous validation functions remain the same]
def validate_whatsapp(number: str) -> bool:
    pattern = r'^\+\d{1,3}\d{10}$'
    return bool(re.match(pattern, number))

def validate_one_liner(text: str) -> bool:
    return len(text) <= 250

def validate_description(text: str) -> bool:
    return len(text.split()) <= 100

def get_all_projects() -> List[Dict]:
    conn = sqlite3.connect('ai_projects.db')
    df = pd.read_sql_query('SELECT * FROM projects ORDER BY date_added DESC', conn)
    conn.close()
    return df.to_dict('records')

def update_project(project_data: Dict) -> tuple:
    """Update existing project in database and sync to Google Sheets"""
    try:
        conn = sqlite3.connect('ai_projects.db')
        c = conn.cursor()
        c.execute('''
            UPDATE projects 
            SET one_liner = ?,
                description = ?,
                ai_usage = ?,
                lead_name = ?,
                whatsapp_contact = ?,
                status = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE project_name = ?
        ''', (
            project_data['one_liner'],
            project_data['description'],
            project_data['ai_usage'],
            project_data['lead_name'],
            project_data['whatsapp_contact'],
            project_data['status'],
            project_data['project_name']
        ))
        conn.commit()
        conn.close()

        # Sync to Google Sheets
        sheets_success, sheets_message = sync_to_sheets(project_data, is_update=True)
        if not sheets_success:
            return True, f"Project updated in database, but {sheets_message}"

        return True, "Project successfully updated and synced to Google Sheets!"
    except Exception as e:
        return False, f"Error: {str(e)}"

def add_project(project_data: Dict) -> tuple:
    """Add new project to database and sync to Google Sheets"""
    try:
        conn = sqlite3.connect('ai_projects.db')
        c = conn.cursor()
        c.execute('''
            INSERT INTO projects 
            (project_name, one_liner, description, ai_usage, lead_name, whatsapp_contact, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            project_data['project_name'],
            project_data['one_liner'],
            project_data['description'],
            project_data['ai_usage'],
            project_data['lead_name'],
            project_data['whatsapp_contact'],
            project_data['status']
        ))
        conn.commit()
        conn.close()

        # Sync to Google Sheets
        sheets_success, sheets_message = sync_to_sheets(project_data)
        if not sheets_success:
            return True, f"Project registered in database, but {sheets_message}"

        return True, "Project successfully registered and synced to Google Sheets!"
    except sqlite3.IntegrityError:
        return False, "Project name already exists!"
    except Exception as e:
        return False, f"Error: {str(e)}"

def search_projects(query: str, projects: List[Dict]) -> List[Dict]:
    query = query.lower()
    return [
        project for project in projects
        if query in project['project_name'].lower() or
        query in project['one_liner'].lower() or
        query in project['description'].lower() or
        query in project['lead_name'].lower()
    ]

def main():
    st.set_page_config(
        page_title="AI Guild Projects Tracker",
        page_icon="🤖",
        layout="wide"
    )

    # Initialize database
    init_db()

    # Main navigation
    st.title("🤖 AI Guild Project Tracker")

    # Create all tabs
    tabs = st.tabs(["View Projects", "Register Project", "Edit Projects"])

    # View Projects Tab
    # View Projects Tab
    with tabs[0]:
        st.header("AI Projects Overview")
        
        # Get all projects
        projects = get_all_projects()
        
        # Calculate metrics
        total_projects = len(projects)
        idea_projects = len([p for p in projects if p['status'] == 'Idea'])
        mvp_projects = len([p for p in projects if p['status'] == 'MVP'])
        launch_projects = len([p for p in projects if p['status'] == 'Launch'])
        
        # Create metrics dashboard
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="Total Registered Projects",
                value=total_projects,
                help="Total number of projects registered in the system"
            )
        
        with col2:
            st.metric(
                label="Projects in Idea Stage",
                value=idea_projects,
                help="Projects in initial concept stage"
            )
        
        with col3:
            st.metric(
                label="Projects in MVP Stage",
                value=mvp_projects,
                help="Projects with working prototype"
            )
        
        with col4:
            st.metric(
                label="Projects in Launch Stage",
                value=launch_projects,
                help="Projects that are live and being used"
            )
        
        # Add a separator
        st.divider()
        
        # Existing search and project listing
        search_query = st.text_input("🔍 Search projects", "")
        
        if search_query:
            filtered_projects = search_projects(search_query, projects)
        else:
            filtered_projects = projects

        if not filtered_projects:
            st.info("No projects found.")
        else:
            for project in filtered_projects:
                status_color = PROJECT_STATUSES[project['status']]['color']
                with st.expander(
                    f"📱 {project['project_name']} - {project['one_liner']} "
                    f"[{project['status']}]"
                ):
                    cols = st.columns(2)
                    with cols[0]:
                        st.markdown("**Project Details**")
                        st.write("**Description:**", project['description'])
                        st.write("**AI Usage:**", project['ai_usage'])
                        st.markdown(f"""
                        **Status:** <span style='color:{status_color}'>{project['status']}</span>
                        """, unsafe_allow_html=True)
                        st.info(PROJECT_STATUSES[project['status']]['description'])
                    with cols[1]:
                        st.markdown("**Contact Information**")
                        st.write("**Project Lead:**", project['lead_name'])
                        st.write("**WhatsApp:**", project['whatsapp_contact'])
                        st.write("**Added on:**", project['date_added'])
                        if project['last_updated'] != project['date_added']:
                            st.write("**Last updated:**", project['last_updated'])

    # Register Project Tab
    with tabs[1]:
        st.header("Register New AI Project")
        
        with st.form("project_registration"):
            project_name = st.text_input("Project Name*")
            one_liner = st.text_input("Project One-liner* (max 250 characters)")
            description = st.text_area("Project Description* (max 100 words)")
            ai_usage = st.text_area("How AI is Used in the Project*")
            lead_name = st.text_input("Project Lead Name*")
            whatsapp_contact = st.text_input("WhatsApp Contact* (format: +[country code][number], e.g., +2347012345678)")
            
            # Add status selection with tooltip
            status = st.selectbox(
                "Project Status*",
                options=list(PROJECT_STATUSES.keys()),
                help="Select the current stage of your project"
            )
            st.info(PROJECT_STATUSES[status]['description'])

            submitted = st.form_submit_button("Register Project")

            if submitted:
                if not all([project_name, one_liner, description, ai_usage, lead_name, whatsapp_contact]):
                    st.error("Please fill all required fields!")
                    return

                if not validate_one_liner(one_liner):
                    st.error("One-liner exceeds 250 characters!")
                    return
                
                if not validate_description(description):
                    st.error("Description exceeds 100 words!")
                    return

                if not validate_whatsapp(whatsapp_contact):
                    st.error("Invalid WhatsApp number format! Use format: +[country code][number]")
                    return

                success, message = add_project({
                    'project_name': project_name,
                    'one_liner': one_liner,
                    'description': description,
                    'ai_usage': ai_usage,
                    'lead_name': lead_name,
                    'whatsapp_contact': whatsapp_contact,
                    'status': status
                })

                if success:
                    st.success(message)
                else:
                    st.error(message)

    # Edit Projects Tab (Protected - Admin Only)
    # Edit Projects Tab (Protected - Admin Only)
    with tabs[2]:
        st.header("Edit Projects")
        
        # Add authentication check only for edit tab
        if not check_password():
            st.warning("Please log in to access the edit functionality")
            return
            
        # Rest of edit tab content only shown after authentication
        all_projects = get_all_projects()
        if not all_projects:
            st.info("No projects available to edit.")
            return
            
        col1, col2 = st.columns([3, 1])
        
        with col1:
            project_to_edit = st.selectbox(
                "Select Project to Edit",
                options=[p['project_name'] for p in all_projects],
                index=None,
                placeholder="Choose a project..."
            )
        
        if project_to_edit:
            with col2:
                delete_button = st.button("🗑️ Delete Project", type="secondary")
                
                if delete_button:
                    st.warning(f"Are you sure you want to delete {project_to_edit}?")
                    confirm_col1, confirm_col2 = st.columns([1, 3])
                    with confirm_col1:
                        if st.button("Yes, Delete", key="confirm_delete"):
                            success, message = delete_project(project_to_edit)
                            if success:
                                st.success(message)
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(message)
                    with confirm_col2:
                        if st.button("Cancel", key="cancel_delete"):
                            st.rerun()
            
            current_project = next(p for p in all_projects if p['project_name'] == project_to_edit)
            
            # Rest of your edit form code remains the same...
                            
            # current_project = next(p for p in all_projects if p['project_name'] == project_to_edit)
            
            with st.form("project_edit"):
                # Pre-fill form with current values
                one_liner = st.text_input(
                    "Project One-liner* (max 250 characters)",
                    value=current_project['one_liner']
                )
                description = st.text_area(
                    "Project Description* (max 100 words)",
                    value=current_project['description']
                )
                ai_usage = st.text_area(
                    "How AI is Used in the Project*",
                    value=current_project['ai_usage']
                )
                lead_name = st.text_input(
                    "Project Lead Name*",
                    value=current_project['lead_name']
                )
                whatsapp_contact = st.text_input(
                    "WhatsApp Contact*",
                    value=current_project['whatsapp_contact']
                )
                status = st.selectbox(
                    "Project Status*",
                    options=list(PROJECT_STATUSES.keys()),
                    index=list(PROJECT_STATUSES.keys()).index(current_project['status']),
                    help="Select the current stage of your project"
                )
                st.info(PROJECT_STATUSES[status]['description'])

                submitted = st.form_submit_button("Update Project")

                if submitted:
                    if not all([one_liner, description, ai_usage, lead_name, whatsapp_contact]):
                        st.error("Please fill all required fields!")
                        return

                    if not validate_whatsapp(whatsapp_contact):
                        st.error("Invalid WhatsApp number format! Use format: +[country code][number]")
                        return

                    success, message = update_project({
                        'project_name': project_to_edit,
                        'one_liner': one_liner,
                        'description': description,
                        'ai_usage': ai_usage,
                        'lead_name': lead_name,
                        'whatsapp_contact': whatsapp_contact,
                        'status': status
                    })

                    if success:
                        st.success(message)
                    else:
                        st.error(message)

if __name__ == "__main__":
    main()