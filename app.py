# This Python code is a Streamlit web application that allows users to create dynamic forms, fill out
# those forms, and view the submitted data. Here is a breakdown of the main functionalities:

import streamlit as st
from db import *
from form_utils import *
import json
import os
import pandas as pd
import re
import datetime
from streamlit.runtime.uploaded_file_manager import UploadedFile
from typing import List, Dict
import hashlib
from dotenv import load_dotenv
load_dotenv()
# Initialize session state
if 'user' not in st.session_state:
    st.session_state.user = None

initialize_default_users()
# Initialize database
initialize_database()
# query_params = st.experimental_get_query_params()

if 'token' in st.query_params:
    # If a token is found, force the page to be "Shared Form".
    st.session_state.page = "Shared Form"
# Near the top of your script with other session state initializations

# Role definitions
ROLES = {
    "admin": ["create", "edit", "delete", "view_all", "admin", "view","manage_users", "update_forms"],
    "editor": ["create", "edit", "view","update_forms"],
    "viewer": ["view"]
}

# Default users (for demo - remove in production)
DEFAULT_USERS = {
    "admin": {"password": "admin123", "role": "admin"},
    "editor": {"password": "editor123", "role": "editor"},
    "viewer": {"password": "viewer123", "role": "viewer"}
}
from werkzeug.security import check_password_hash

def authenticate_user(username: str, password: str) -> Optional[Dict]:
    """Verify against hashed passwords"""
    user = get_user(username)
    if user and check_password_hash(user['password_hash'], password):
        return {
            "id": user['id'],
            "username": user['username'],
            "role": user['role'],
            "permissions": ROLES.get(user['role'], [])
        }
    return None

def check_access(required_permission: str):
    """Skip auth check for auth page"""
    if st.session_state.page == "Authentication":
        return
        
    if not st.session_state.user:
        st.warning("Please login to access this page")
        st.session_state.page = "Authentication"
        st.rerun()
    
    if required_permission not in st.session_state.user.get("permissions", []):
        st.error(f"Insufficient permissions for {st.session_state.user['role']} role")
        st.stop()
def display_share_options(form_name: str):
    """
    Renders the UI for generating, displaying, and revoking a form's share link.
    This is a reusable component for the Create and Update pages.
    
    Args:
        form_name (str): The name of the form to manage share options for.
    """
    if not form_name:
        return

    st.subheader("🔗 Share Form")
    st.info(f"Generate a unique, public link for the form: **'{form_name}'**")

    # Get the current token for this specific form
    current_token = get_share_token(form_name)

    if st.button(f"Generate / Regenerate Share Link for '{form_name}'"):
        import uuid
        new_token = str(uuid.uuid4())
        if set_form_share_token(form_name, new_token):
            st.success("Share link created/updated successfully!")
            st.rerun()  # Rerun to display the new link immediately
        else:
            st.error("Failed to create share link.")

    if current_token:
        base_url = os.getenv("BASE_URL", "http://localhost:8501")
        share_url = f"{base_url}?token={current_token}"
        st.success("This form is shareable! Copy the link or embed code below.")
        
        st.markdown("**Public URL**")
        st.code(share_url, language="text")
        
        st.markdown("**Embed Code**")
        embed_code = generate_embed_code(form_name, current_token, base_url)
        st.code(embed_code, language="html")
        
        if st.button(f"Revoke Access for '{form_name}'", type="primary"):
            if set_form_share_token(form_name, None): # Set token to NULL in DB
                st.success("Access revoked successfully!")
                st.rerun()
            else:
                st.error("Failed to revoke access.")
# Page navigation
pages = {
    "Authentication": "auth",
    "Form Creation": "create",
    "Shared Form":"Shared",
    "Form Filling": "fill",
    "Update Forms": "update_form" ,
    "Admin View": "admin",
    "User Management": "users"
}
# Navigation sidebar
st.sidebar.title("Navigation")

if st.session_state.user:
    # Show all pages except auth for logged-in users
    st.session_state.page = st.sidebar.radio(
        "Go to",
        [p for p in pages.keys() if p != "Authentication"],
        index=0
    )
else:
    # Only show auth page for non-logged-in users
    st.session_state.page = "Authentication"
if st.session_state.user:
    if st.sidebar.button("Logout",key="logout_button"):
        st.session_state.user = None
        st.rerun()
    st.sidebar.write(f"Logged in as: {st.session_state.user['username']} ({st.session_state.user['role']})")
# Password protection
if 'create_unlocked' not in st.session_state:
    st.session_state.create_unlocked = False
if 'admin_unlocked' not in st.session_state:
    st.session_state.admin_unlocked = False
if 'active_auth_tab' not in st.session_state:
    st.session_state.active_auth_tab = "Login"
#Initialize page variable at the top
if 'page' not in st.session_state:
    st.session_state.page = "auth"
# Add this auth page handler
if st.session_state.page == "Authentication":
    st.title("Authentication")
    
    if st.session_state.user:
        st.warning("You are already logged in")
        if st.button("Logout"):
            st.session_state.user = None
            st.rerun()
        st.stop()
    
    tab1, tab2, tab3 = st.tabs(["Login", "Register", "Reset Password"])
    
    with tab1:  # Login tab
        with st.form("login_form"):
            st.subheader("Login to Your Account")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            
            if st.form_submit_button("Login"):
                user = authenticate_user(username, password)
                if user:
                    st.session_state.user = user
                    # Redirect based on role
                
                    if user["role"] == "viewer":
                        st.session_state.page = "fill"
                    st.success("Login successful! Redirecting...")
                    # st.rerun()
                else:
                    st.error("Invalid credentials")
    
    with tab2:  # Register tab
        with st.form("registration_form"):
            st.subheader("Create New Account")
            new_username = st.text_input("Username")
            new_password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            
            if st.form_submit_button("Register"):
                
                if not new_username or not new_password:
                    st.error("Please provide both username and password")
                elif new_password != confirm_password:
                    st.error("Passwords do not match")
                elif not is_username_available(new_username):
                    st.error("Username already taken")
                else:
                    if register_user(new_username, new_password):
                        st.success("Registration successful! Please login.")
                        # Switch to login tab after successful registration
                        st.session_state.active_auth_tab = "Login"
                        st.rerun()
                    else:
                        st.error("Registration failed. Please try again.")
    with tab3:  # Password reset tab
        with st.form("reset_form"):
            st.subheader("Reset Your Password")
            reset_username = st.text_input("Your Username")
            new_password = st.text_input("New Password", type="password")
            confirm_password = st.text_input("Confirm New Password", type="password")
            
            if st.form_submit_button("Reset Password"):
                if new_password != confirm_password:
                    st.error("Passwords don't match!")
                elif not is_username_available(reset_username):  # User exists
                    if reset_user_password(reset_username, new_password):
                        st.success("Password reset successfully! Please login with your new password.")
                    else:
                        st.error("Password reset failed")
                else:
                    st.error("Username not found")
# Form Creation Page
elif st.session_state.page == "Form Creation":
    st.title("Form Generator")
    check_access("create")
    # If a form was just submitted, reset the state before drawing widgets
    if st.session_state.get('form_submitted_successfully', False):
        st.session_state.form_name = ""
        st.session_state.fields = []
        st.session_state.prev_form_name = ""
        # IMPORTANT: Reset the flag
        st.session_state.form_submitted_successfully = False
    
    # selected_form = st.selectbox("Select Form to Edit", existing_forms)
    if 'fields' not in st.session_state:
        st.session_state.fields = []
    
    # Track previous form name to detect changes
    if 'prev_form_name' not in st.session_state:
        st.session_state.prev_form_name = ""
    
    form_name = st.text_input("Form Name", 
        value=st.session_state.get('form_name', ''),
        key="form_name")
    existing_forms = [f for f in get_all_forms() if f != form_name and form_name not in get_child_forms(f)]
    if existing_forms:
        parent_form = st.selectbox("Link to Parent Form (optional)", 
            [""] + existing_forms)
    else:
        parent_form = "None "
    
    # Reset fields if form name changes
    if form_name and form_name != st.session_state.prev_form_name:
        st.session_state.fields = []
        st.session_state.prev_form_name = form_name
    
    # Field input section
    st.subheader("Form Fields")
    col1, col2, col3 = st.columns([3, 2, 1])
    with col1:
        new_field = st.text_input("Field Name", key="new_field")
    with col2:
        field_type = st.selectbox(
            "Data Type",
            [
                "VARCHAR(255)", "INTEGER", "FLOAT", "DATE", "BOOLEAN", "TEXT", 
                "PHONE", "TEXTAREA", "PASSWORD", "CHECKBOX", "RADIO", "SELECT", 
                "DATETIME", "TIME", "MULTISELECT", "EMAIL", "URL", "COLOR", 
                "FILE", "RANGE"
            ],
            key="field_type"
        )
    with col3:
        st.write("")
        st.write("")
        if st.button("Add Field"):
            if new_field:
                if field_type in ["SELECT", "RADIO", "CHECKBOX", "MULTISELECT"]:
                    st.session_state.field_options = True
                else:
                    st.session_state.fields.append({"name": new_field, "type": field_type})
                    st.success(f"Added field: {new_field}")
    
    # Handle field options for specific types
    if 'field_options' in st.session_state and st.session_state.field_options:
        with st.expander("Field Options"):
            options_input = st.text_input(
                "Options (comma separated)", 
                key=f"options_{new_field}"
            )
            if st.button("Save Options"):
                if options_input:
                    options = [opt.strip() for opt in options_input.split(",")]
                    st.session_state.fields.append({
                        "name": new_field, 
                        "type": field_type,
                        "options": options
                    })
                    st.success(f"Added field: {new_field} with options")
                    del st.session_state.field_options
                else:
                    st.warning("Please provide options for this field type")
    
    # Display current fields with remove options
    if st.session_state.fields:
        st.subheader("Current Fields")
        for i, field in enumerate(st.session_state.fields):
            col1, col2, col3, col4 = st.columns([4, 3, 2, 1])
            with col1:
                # Allow editing field name
                new_name = st.text_input("Field", value=field['name'], 
                    key=f"field_{i}")
                # Update name if changed
                if new_name != field['name']:
                    st.session_state.fields[i]['name'] = new_name
            with col2:
                # Editable field type
                new_type = st.selectbox(
                    "Type",
                    [
                        "VARCHAR(255)", "INTEGER", "FLOAT", "DATE", "BOOLEAN", "TEXT", 
                        "PHONE", "TEXTAREA", "PASSWORD", "CHECKBOX", "RADIO", "SELECT", 
                        "DATETIME", "TIME", "MULTISELECT", "EMAIL", "URL", "COLOR", 
                        "FILE", "RANGE"
                    ],
                    index=[
                        "VARCHAR(255)", "INTEGER", "FLOAT", "DATE", "BOOLEAN", "TEXT", 
                        "PHONE", "TEXTAREA", "PASSWORD", "CHECKBOX", "RADIO", "SELECT", 
                        "DATETIME", "TIME", "MULTISELECT", "EMAIL", "URL", "COLOR", 
                        "FILE", "RANGE"
                    ].index(field['type']),
                    key=f"type_{i}"
                )
                # Update type if changed
                if new_type != field['type']:
                    st.session_state.fields[i]['type'] = new_type
            with col3:
                # Show options if applicable
                if new_type in ["SELECT", "RADIO", "CHECKBOX", "MULTISELECT"]:
                    current_options = field.get('options', [])
                    options_input = st.text_input(
                        "Options", 
                        value=", ".join(current_options) if current_options else "",
                        key=f"options_{i}"
                    )
                    if options_input:
                        st.session_state.fields[i]['options'] = [opt.strip() for opt in options_input.split(",")]
            with col4:
                if st.button("❌ Remove", key=f"remove_{i}"):
                    st.session_state.fields.pop(i)
                    st.rerun()
    # NEW, IMPROVED CODE
# In the "Generate Form" button section
    if st.button("🚀 Generate Form Instantly", type="primary"):
        if form_name and st.session_state.fields:
            try:
                # Save form metadata and get form ID
                form_id = save_form_metadata(form_name, st.session_state.fields)
                
                # This handles the case where a form with the same name exists
                if form_id is None:
                    st.error(f"A form with the name '{form_name}' might already exist or there was a database error.")
                    st.stop()
                
                # Create database table
                if not create_dynamic_table(form_name, st.session_state.fields):
                    st.error("Failed to create the database table for the form.")
                    st.stop()
                    
                # --- FASTER GENERATION ---
                # Use the new, instant HTML generator by default
                html_content = generate_html_form(form_name, st.session_state.fields)
                filepath = save_form_html(form_name, html_content)
                
                # Set permissions for the creator
                if st.session_state.user:
                    set_form_permission(
                        form_id=form_id,
                        user_id=st.session_state.user["id"],
                        can_view=True, can_edit=True, can_delete=True
                    )
                
                # Handle parent-child relationship
                if parent_form:
                    success, message = link_child_to_parent(form_name, parent_form)
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                    
                st.success("Form generated successfully!")
                st.subheader("Form Preview")
                st.components.v1.html(html_content, height=500, scrolling=True)
                st.session_state.form_submitted_successfully = True
            
                # Provide an OPTIONAL button to enhance with LLM
                st.info("The form is ready to use. You can optionally use the LLM to try and improve the styling.")
                if st.button("✨ Enhance with AI (may be slow)"):
                    with st.spinner(f"Sending '{form_name}' to the AI for enhancement... This may take a moment."):
                        
                        # Ensure fields are hashable for caching if you use @lru_cache on generate_form_with_llama
                        # This is a good practice to prevent potential errors.
                        try:
                            fields_tuple = tuple(tuple(d.items()) for d in st.session_state.fields)
                            enhanced_html = generate_form_with_llama(form_name, fields_tuple)
                        except Exception as e:
                            st.error(f"AI enhancement failed: {e}")
                            enhanced_html = None # Ensure a value is set
                        if enhanced_html:
                            save_form_html(form_name, enhanced_html)
                            st.success("AI enhancement complete!")
                            st.subheader("Enhanced Form Preview")
                            st.components.v1.html(enhanced_html, height=500, scrolling=True)
                
                
            except Exception as e:
                st.error(f"Form generation failed: {str(e)}")
                # ... (keep your existing error handling) ...
        else:
            st.warning("Please provide a form name and at least one field.")    
    st.divider()
    st.subheader("Share Form")
    
    # Generate or get existing token
    # Generate or get existing token
    if 'share_token' not in st.session_state or st.session_state.get('current_form_for_token') != form_name:
        st.session_state.share_token = get_share_token(form_name) or ""
        st.session_state.current_form_for_token = form_name
    
    if st.button("Generate Share Link"):
        import uuid
        new_token = str(uuid.uuid4())
        if set_form_share_token(form_name, new_token):
            st.session_state.share_token = new_token
            st.success("Share token created!")
        else:
            st.error("Failed to create share token")
    
    if st.session_state.share_token:
        base_url = os.getenv("BASE_URL", "http://localhost:8501")
        share_url = f"{base_url}/?token={st.session_state.share_token}"
        st.success("Form is shareable! Copy the link below:")
        st.code(share_url, language="text")
        
        # Embedding option
        st.subheader("Embed Form")
        embed_code = generate_embed_code(form_name, st.session_state.share_token, base_url)
        st.code(embed_code, language="html")
        
        if st.button("Revoke Access"):
            if set_form_share_token(form_name, None):
                st.session_state.share_token = ""
                st.success("Access revoked!")
            else:
                st.error("Failed to revoke access")

# Form Filling Page
elif st.session_state.page == "Form Filling":
    st.title("Fill Form")
    check_access("view")
    
    # Initialize tab management
    if 'form_tabs' not in st.session_state:
        st.session_state.form_tabs = []
        st.session_state.active_tab = None
    
    # Tab management UI
    st.subheader("Open Forms")
    
    # Create columns for tabs + new tab button
    tab_cols = st.columns([8, 1])
    
    with tab_cols[0]:
        # Show existing tabs
        if st.session_state.form_tabs:
            tab_titles = [f"Form {i+1}: {tab['form_name']}" for i, tab in enumerate(st.session_state.form_tabs)]
            selected_tab_idx = st.radio(
                "Active Tab",
                range(len(st.session_state.form_tabs)),
                format_func=lambda i: tab_titles[i],
                horizontal=True,
                label_visibility="collapsed"
            )
            st.session_state.active_tab = selected_tab_idx
            
    with tab_cols[1]:
        if st.button("+ New", help="Open new form tab"):
            # Add new empty tab
            st.session_state.form_tabs.append({
                "form_name": "",
                "fields": None,
                "form_data": {},
                "parent_id": None
            })
            st.session_state.active_tab = len(st.session_state.form_tabs) - 1
            st.rerun()
    
    # Close tab button
    if st.session_state.form_tabs:
        if st.button("✕ Close", help="Close current tab"):
            if st.session_state.active_tab is not None:
                st.session_state.form_tabs.pop(st.session_state.active_tab)
                if st.session_state.form_tabs:
                    st.session_state.active_tab = min(st.session_state.active_tab, len(st.session_state.form_tabs)-1)
                else:
                    st.session_state.active_tab = None
                st.rerun()
    
    # Main form area
    if st.session_state.active_tab is not None:
        tab_data = st.session_state.form_tabs[st.session_state.active_tab]
        
        # Form selection for the active tab
        forms = get_all_forms()
        form_name = st.selectbox(
            "Select Form", 
            forms,
            index=forms.index(tab_data["form_name"]) if tab_data["form_name"] in forms else 0,
            key=f"form_select_{st.session_state.active_tab}"
        )
        
        # Update tab when form changes
        if form_name != tab_data["form_name"]:
            tab_data["form_name"] = form_name
            tab_data["fields"] = get_form_fields(form_name)
            tab_data["form_data"] = {}
            tab_data["parent_id"] = None  # Reset parent ID when form changes
            st.rerun()
        
        # Only proceed if form is selected
        if form_name:
            tab_data["fields"] = tab_data["fields"] or get_form_fields(form_name)
            fields = tab_data["fields"]
            
            # Validate fields structure
            if not fields or not isinstance(fields, list):
                st.error("Invalid form fields configuration")
                st.stop()
                
            st.subheader(f"Fill {form_name}")
            
            # Parent form handling - improved version
            parent_id = tab_data["parent_id"]
            parent_form = None
            
            # Only try to get parent forms if we have a form_name selected
            if form_name:
                parent_forms = get_parent_forms(form_name)
                if parent_forms and isinstance(parent_forms, list) and len(parent_forms) > 0:
                    parent_form = parent_forms[0]
                    parent_records = get_form_data(parent_form) if parent_form else []
                    
                    if parent_records:
                        parent_options = {f"ID: {r['id']} - {r.get('name', '')}"[:50]: r['id'] for r in parent_records}
                        selected_parent = st.selectbox(
                            f"Select {parent_form} record", 
                            options=list(parent_options.keys()),
                            key=f"parent_select_{st.session_state.active_tab}"
                        )
                        parent_id = parent_options[selected_parent]
                        tab_data["parent_id"] = parent_id
                    else:
                        st.warning(f"No {parent_form} records available. Please create one first.")
                        st.stop()
            
            # Use a form context to prevent partial submissions
            with st.form(key=f"form_{form_name}_{st.session_state.active_tab}"):
                form_data = {}
                validation_errors = []
                
                # Render form fields with enhanced validation
                for i, field in enumerate(fields):
                    try:
                        # Validate field structure
                        if not isinstance(field, dict):
                            st.error(f"Invalid field at position {i}: Expected dict, got {type(field)}")
                            continue
                            
                        # Validate field name
                        if "name" not in field:
                            st.error(f"Field at position {i} is missing 'name' property")
                            continue
                            
                        field_name = field["name"]
                        if not isinstance(field_name, str):
                            st.error(f"Field name at position {i} must be string, got {type(field_name)}")
                            continue
                            
                        field_name = field_name.strip()
                        if not field_name:
                            st.error(f"Field name at position {i} is empty")
                            continue
                            
                        # Get field type with default
                        field_type = field.get("type", "TEXT")
                        if not isinstance(field_type, str):
                            st.error(f"Field type at position {i} must be string, got {type(field_type)}")
                            continue
                            
                        # Handle different field types
                        if field_type == "TEXTAREA":
                            form_data[field_name] = st.text_area(field_name)
                        
                        elif field_type == "PASSWORD":
                            form_data[field_name] = st.text_input(field_name, type="password")
                        
                        elif field_type == "CHECKBOX":
                            if "options" in field:
                                selected = []
                                for option in field["options"]:
                                    if st.checkbox(f"{field_name} - {option}", key=f"checkbox_{field_name}_{option}_{i}"):
                                        selected.append(option)
                                form_data[field_name] = ", ".join(selected) if selected else None
                        
                        elif field_type == "RADIO":
                            if "options" in field:
                                form_data[field_name] = st.radio(field_name, field["options"], key=f"radio_{field_name}_{i}")
                        
                        elif field_type == "SELECT":
                            if "options" in field:
                                form_data[field_name] = st.selectbox(field_name, field["options"], key=f"select_{field_name}_{i}")
                        
                        elif field_type == "DATETIME":
                            col1, col2 = st.columns(2)
                            with col1:
                                date_value = st.date_input(f"{field_name} (date)", key=f"date_{field_name}_{i}")
                            with col2:
                                time_value = st.time_input(f"{field_name} (time)", key=f"time_{field_name}_{i}")
                            
                            # Combine date and time into a datetime string
                            if date_value and time_value:
                                form_data[field_name] = f"{date_value} {time_value}"
                            else:
                                form_data[field_name] = None
                        elif field_type == "TIME":
                            form_data[field_name] = st.time_input(field_name, key=f"time_{field_name}_{i}")
                        
                        elif field_type == "MULTISELECT":
                            if "options" in field:
                                form_data[field_name] = st.multiselect(field_name, field["options"], key=f"multiselect_{field_name}_{i}")
                        
                        elif field_type == "EMAIL":
                            email = st.text_input(field_name, key=f"email_{field_name}_{i}")
                            if email and not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                                validation_errors.append(f"{field_name} must be a valid email address")
                            form_data[field_name] = email
                        
                        elif field_type == "URL":
                            url = st.text_input(field_name, key=f"url_{field_name}_{i}")
                            if url and not re.match(r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+", url):
                                validation_errors.append(f"{field_name} must be a valid URL")
                            form_data[field_name] = url
                        
                        elif field_type == "COLOR":
                            form_data[field_name] = st.color_picker(field_name, key=f"color_{field_name}_{i}")
                        
                        elif field_type == "FILE":
                            form_data[field_name] = st.file_uploader(field_name, key=f"file_{field_name}_{i}")
                        
                        elif field_type == "RANGE":
                            min_val, max_val = 0, 100  # Default range
                            if "options" in field and len(field["options"]) >= 2:
                                try:
                                    min_val = float(field["options"][0])
                                    max_val = float(field["options"][1])
                                except ValueError:
                                    pass
                            form_data[field_name] = st.slider(field_name, min_val, max_val, key=f"slider_{field_name}_{i}")
                        
                        # Handle original field types
                        elif field_name.lower() == "gender":
                            options = ["Male", "Female", "Other", "Prefer not to say"]
                            form_data[field_name] = st.selectbox(field_name, options, key=f"gender_{i}")
                        
                        elif field_type == "PHONE":
                            phone = st.text_input(field_name, key=f"phone_{field_name}_{i}")
                            if phone and (not phone.isdigit() or len(phone) != 10):
                                validation_errors.append(f"{field_name} must be a 10-digit number")
                            form_data[field_name] = phone
                        
                        elif "VARCHAR" in field_type or "TEXT" in field_type:
                            form_data[field_name] = st.text_input(field_name, key=f"text_{field_name}_{i}")
                        
                        elif "INT" in field_type:
                            form_data[field_name] = st.number_input(field_name, step=1, key=f"int_{field_name}_{i}")
                        
                        elif "FLOAT" in field_type:
                            form_data[field_name] = st.number_input(field_name, step=0.1, key=f"float_{field_name}_{i}")
                        
                        elif "DATE" in field_type:
                            min_date = datetime.date(1800, 1, 1)
                            max_date = datetime.date.today()
                            form_data[field_name] = st.date_input(
                                field_name,
                                min_value=min_date,
                                max_value=max_date,
                                key=f"date_{field_name}_{i}"
                            )
                        
                        elif "BOOLEAN" in field_type:
                            form_data[field_name] = st.checkbox(field_name, key=f"checkbox_{field_name}_{i}")
                    
                    except Exception as e:
                        st.error(f"Error rendering field {i}: {str(e)}")
                        logger.exception(f"Error rendering field {i}")
                
                # Display validation errors
                for error in validation_errors:
                    st.error(error)
                
                tab_data["form_data"] = form_data
                
                # Submit button inside the form context
                submitted = st.form_submit_button("Submit Form")
                
            if submitted and not validation_errors:
                    
                try:
                    # Check if form has valid data
                    has_data = False
                    for value in form_data.values():
                        if value not in (None, "", [], [""]):
                            has_data = True
                            break
                        
                    if not has_data:
                        st.error("Please fill in at least one field")
                        st.stop()
                    # First, validate we have actual data to save
                    if not form_data or all(v in (None, "", [], {}) for v in form_data.values()):
                        st.error("Please fill in at least one field")
                        st.stop()
                    # Convert data types before submission
                    processed_data = {}
                    field_errors = []
                        
                    for i, field in enumerate(fields):
                        try:
                            # Skip if field is invalid
                            if not isinstance(field, dict) or "name" not in field:
                                continue
                                    
                            field_name = field["name"]
                            if not isinstance(field_name, str) or not field_name.strip():
                                continue
                                    
                            # Normalize field name
                            normalized_name = field_name.strip().replace(" ", "_").lower()
                                
                            # Skip id field
                            if normalized_name == "id":
                                continue
                                
                            # Skip if field not in form data
                            if field_name not in form_data:
                                continue
                                    
                            value = form_data[field_name]
                                
                            # Skip empty values
                            if value in (None, "", [], [""]):
                                if field.get("required"):
                                    field_errors.append(f"{field_name} is required")
                                continue
                                
                            # Get field type with default
                            field_type = field.get("type", "TEXT")
                                
                            # Type conversions
                            if field_type == "BOOLEAN":
                                processed_data[normalized_name] = bool(value) if not isinstance(value, str) else value.lower() in ('true', 't', 'yes', 'y', '1', 'on')
                                
                            elif field_type in ["CHECKBOX", "MULTISELECT"]:
                                if isinstance(value, str):
                                    processed_data[normalized_name] = [v.strip() for v in value.split(',') if v.strip()]
                                elif isinstance(value, (list, tuple)):
                                    processed_data[normalized_name] = list(value)
                                else:
                                    processed_data[normalized_name] = [str(value)]
                                
                            elif field_type in ["DATE", "DATETIME", "TIME"]:
                                if hasattr(value, 'isoformat'):
                                    if isinstance(value, datetime.time):
                                        processed_data[normalized_name] = value.strftime("%H:%M:%S")
                                    elif isinstance(value, datetime.datetime):
                                        processed_data[normalized_name] = value.strftime("%Y-%m-%d %H:%M:%S")
                                    else:  # date
                                        processed_data[normalized_name] = value.isoformat()
                                else:
                                    processed_data[normalized_name] = value
                            elif field_type == "INTEGER":
                                try:
                                    processed_data[normalized_name] = int(float(value)) if value else None
                                except (ValueError, TypeError):
                                    field_errors.append(f"Invalid integer value for {field_name}")
                                
                            elif field_type == "FLOAT":
                                try:
                                    processed_data[normalized_name] = float(value) if value else None
                                except (ValueError, TypeError):
                                    field_errors.append(f"Invalid number for {field_name}")
                            else:
                                processed_data[normalized_name] = value
                            
                        except Exception as e:
                            logger.exception(f"Error processing field {i} ({field_name})")
                            field_errors.append(f"Error processing {field_name}: {str(e)}")
                        
                    # Show field errors if any
                    if field_errors:
                        for error in field_errors:
                            st.error(error)
                        st.stop()
                        
                    # Handle parent-child relationship - safer version
                    if parent_id and parent_form:  # Only check if we have both
                        if not record_exists(parent_form, parent_id):
                            st.error(f"The selected {parent_form} record (ID: {parent_id}) no longer exists")
                            st.stop()
                        processed_data['parent_id'] = parent_id
                        
                    # Debug preview for admins
                    if st.session_state.user.get('role') == 'admin':
                        with st.expander("Debug Preview"):
                            st.write("Data to save:", processed_data)
                            st.write("Fields structure:", fields)
                            try:
                                debug_info = debug_save_operation(form_name, processed_data)
                                st.write("Table exists:", debug_info["table_exists"])
                                st.write("Columns:", debug_info["columns"])
                                st.write("Constraints:", debug_info["constraints"])
                            except Exception as e:
                                st.error(f"Debug error: {str(e)}")
                        
                    # Check if we have data to save
                    if not processed_data:
                        st.error("No data to save. Please fill in at least one field.")
                        st.stop()
                            
                    # Schema synchronization
                    if not synchronize_form_table(form_name):
                        st.error("Database schema out of sync. Please try again.")
                        st.stop()
                    # Get form data
                    form_data = get_form_data(form_name)  # Your function to collect form data
                        
                    # Check if we already processed this submission
                    current_hash = hashlib.md5(str(form_data).encode()).hexdigest()
                        
                    if 'last_submission_hash' in st.session_state:
                        if st.session_state.last_submission_hash == current_hash:
                            st.warning("This submission has already been processed")
                            st.stop()
                    # Save data
                    if save_form_data(form_name, processed_data):
                        st.success("✅ Form submitted successfully!")
                        # Reset form data but keep the tab open
                        tab_data["form_data"] = {}
                        st.balloons()
                    else:
                        st.error("""
                        Failed to save form data. Possible reasons:
                        1. Data type mismatch
                        2. Missing required fields
                        3. Database constraints violated
                        """)
                            
                        # Show detailed error for admins
                        if st.session_state.user.get('role') == 'admin':
                            with st.expander("Technical Details"):
                                try:
                                    debug_info = debug_save_operation(form_name, processed_data)
                                    st.write("Debug Info:", debug_info)
                                except Exception as e:
                                    st.error(f"Debug error: {str(e)}")
                                    
                                if st.button("Force Table Repair", key=f"repair_{form_name}_{st.session_state.active_tab}"):
                                    if synchronize_form_table(form_name):
                                        st.success("Table repair complete! Please try submitting again.")
                                    st.rerun()
                                else:
                                    st.error("Table repair failed.")
                    
                except Exception as e:
                    st.error(f"Submission error: {str(e)}")
                    logger.exception("Form submission failed")
                    # Add detailed traceback for admins
                    if st.session_state.user.get('role') == 'admin':
                        with st.expander("Technical Details"):
                            st.write("Form data:", form_data)
                            st.write("Processed data:", processed_data)
                            st.write("Fields:", fields)
                            st.write("Full error traceback:")
                            st.exception(e)
elif st.session_state.page == "Shared Form":
    st.title("Public Form")
    
    token = st.query_params.get("token")
    
    if not token:
        st.error("Missing or invalid form token in the URL.")
        st.stop()

    form_meta = get_form_by_token(token)
    if not form_meta:
        st.error("This form link is invalid or has expired.")
        st.stop()

    form_name = form_meta["form_name"]
    fields = form_meta["fields"]
    
    if not fields or not isinstance(fields, list):
        st.error("This form is not configured correctly. Please contact the administrator.")
        st.stop()

    st.subheader(f"You are filling out: {form_name}")
    st.markdown("---")
    
    # Use a form context to handle submission
    with st.form(key=f"shared_form_{token}"):
        form_data = {}
        validation_errors = []

        # --- This is the same robust field rendering logic from the "Form Filling" page ---
        for i, field in enumerate(fields):
            field_name = field.get("name", f"field_{i}")
            field_type = field.get("type", "TEXT")
            
            if field_type == "TEXTAREA":
                form_data[field_name] = st.text_area(field_name)
            elif field_type == "PASSWORD":
                form_data[field_name] = st.text_input(field_name, type="password")
            elif field_type == "RADIO" and "options" in field:
                form_data[field_name] = st.radio(field_name, field["options"], key=f"radio_{field_name}_{i}")
            elif field_type == "SELECT" and "options" in field:
                form_data[field_name] = st.selectbox(field_name, field["options"], key=f"select_{field_name}_{i}")
            elif field_type == "MULTISELECT" and "options" in field:
                form_data[field_name] = st.multiselect(field_name, field["options"], key=f"multiselect_{field_name}_{i}")
            elif field_type == "DATETIME":
                form_data[field_name] = st.date_input(field_name, value=None, key=f"datetime_{field_name}_{i}")
            elif field_type == "EMAIL":
                email = st.text_input(field_name, key=f"email_{field_name}_{i}")
                if email and not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                    validation_errors.append(f"{field_name} must be a valid email address")
                form_data[field_name] = email
            elif "INT" in field_type:
                form_data[field_name] = st.number_input(field_name, step=1, value=None, key=f"int_{field_name}_{i}")
            elif "FLOAT" in field_type:
                form_data[field_name] = st.number_input(field_name, step=0.1, value=None, key=f"float_{field_name}_{i}")
            elif "DATE" in field_type:
                form_data[field_name] = st.date_input(field_name, value=None, key=f"date_{field_name}_{i}")
            elif "BOOLEAN" in field_type:
                form_data[field_name] = st.checkbox(field_name, key=f"checkbox_{field_name}_{i}")
            else: # Default to text input
                form_data[field_name] = st.text_input(field_name, key=f"text_{field_name}_{i}")
        
        # Display validation errors
        for error in validation_errors:
            st.error(error)

        submitted = st.form_submit_button("Submit Form")

        if submitted and not validation_errors:
            # --- This is the same robust data processing logic ---
            processed_data = {}
            for field in fields:
                field_name = field["name"]
                normalized_name = field_name.replace(" ", "_").lower()
                value = form_data.get(field_name)

                if value not in [None, "", [], {}]:
                    processed_data[normalized_name] = value
            
            if not processed_data:
                st.warning("Please fill in at least one field before submitting.")
            else:
                if save_form_data(form_name, processed_data):
                    st.success("✅ Thank you! Your submission has been received.")
                    st.balloons()
                else:
                    st.error("❌ There was an error saving your submission. Please try again.")
# Admin Page
elif st.session_state.page == "Admin View":
    st.title("Admin View")
    check_access("admin")
    
    # Initialize tab management
    if 'admin_tabs' not in st.session_state:
        st.session_state.admin_tabs = []
        st.session_state.active_admin_tab = None
    
    # Tab management UI
    st.subheader("Analysis Tabs")
    
    # Create columns for tabs + new tab button
    tab_cols = st.columns([8, 1])
    
    with tab_cols[0]:
        # Show existing tabs
        if st.session_state.admin_tabs:
            tab_titles = [f"Form: {tab['form_name']}" if tab['form_name'] else "New Tab" 
                    for i, tab in enumerate(st.session_state.admin_tabs)]
            selected_tab_idx = st.radio(
                "Active Tab",
                range(len(st.session_state.admin_tabs)),
                format_func=lambda i: tab_titles[i],
                horizontal=True,
                label_visibility="collapsed"
            )
            st.session_state.active_admin_tab = selected_tab_idx
            
    with tab_cols[1]:
        if st.button("+ New", help="Open new analysis tab"):
            # Add new empty tab
            st.session_state.admin_tabs.append({
                "form_name": "",
                "parent_record": None,
                "data": None
            })
            st.session_state.active_admin_tab = len(st.session_state.admin_tabs) - 1
            st.rerun()
    
    # Close tab button
    if st.session_state.admin_tabs:
        if st.button("✕ Close", help="Close current tab"):
            if st.session_state.active_admin_tab is not None:
                st.session_state.admin_tabs.pop(st.session_state.active_admin_tab)
                if st.session_state.admin_tabs:
                    st.session_state.active_admin_tab = min(st.session_state.active_admin_tab, len(st.session_state.admin_tabs)-1)
                else:
                    st.session_state.active_admin_tab = None
                st.rerun()

    # Main content area
    if st.session_state.active_admin_tab is not None:
        tab = st.session_state.admin_tabs[st.session_state.active_admin_tab]
        
        # Form selection
        forms = get_all_forms()
        form_name = st.selectbox(
            "Select Form", 
            forms,
            index=forms.index(tab["form_name"]) if tab["form_name"] and tab["form_name"] in forms else 0,
            key=f"form_select_{st.session_state.active_admin_tab}"
        )
        
        # Update tab when form changes
        if form_name != tab["form_name"]:
            tab["form_name"] = form_name
            tab["data"] = None
            tab["parent_record"] = None
            st.rerun()
        
        # Load data button
        if st.button("Load Data", key=f"load_{st.session_state.active_admin_tab}"):
            try:
                tab["data"] = get_form_data(form_name)
                st.rerun()
            except Exception as e:
                st.error(f"Error loading data: {str(e)}")
        
        # Only proceed if form is selected and data is loaded
        if form_name and tab["data"] is not None:
            data = tab["data"]
            
            if not data:
                st.warning("No submissions found for this form")
                st.stop()
                
            # Convert to DataFrame for filtering
            df = pd.DataFrame(data).fillna('')
            
            # Create dynamic filters based on column names
            st.subheader("Filters")
            
            # Create columns for filters
            filter_cols = st.columns(4)
            filters = {}
            filter_types = {}
            
            # Function to find matching columns
            def find_matching_columns(pattern):
                pattern = pattern.lower()
                return [col for col in df.columns if pattern in col.lower()]
            
            # Gender filter
            gender_cols = find_matching_columns("gender")
            if gender_cols:
                gender_col = gender_cols[0]  # Use first matching column
                genders = ['All'] + sorted(df[gender_col].astype(str).unique().tolist())
                selected_gender = filter_cols[0].selectbox("Gender", genders)
                if selected_gender != 'All':
                    filters[gender_col] = selected_gender
                    filter_types[gender_col] = "select"
            
            # Age filter
            age_cols = find_matching_columns("age")
            if age_cols:
                age_col = age_cols[0]  # Use first matching column
                try:
                    # Convert to numeric if possible
                    df[age_col] = pd.to_numeric(df[age_col], errors='coerce')
                    if not df[age_col].isnull().all():  # Check if conversion worked
                        min_age = int(df[age_col].min())
                        max_age = int(df[age_col].max())
                        if min_age >= max_age:
                            max_age = min_age + 1
                        
                        age_range = filter_cols[1].slider(
                            "Age Range", 
                            min_value=min_age, 
                            max_value=max_age, 
                            value=(min_age, max_age)
                        )
                        filters[age_col] = age_range
                        filter_types[age_col] = "range"
                    else:
                        # Handle as categorical if conversion failed
                        ages = ['All'] + sorted(df[age_col].astype(str).unique().tolist())
                        selected_age = filter_cols[1].selectbox("Age", ages)
                        if selected_age != 'All':
                            filters[age_col] = selected_age
                            filter_types[age_col] = "select"
                except:
                    # Handle as categorical if any error occurs
                    ages = ['All'] + sorted(df[age_col].astype(str).unique().tolist())
                    selected_age = filter_cols[1].selectbox("Age", ages)
                    if selected_age != 'All':
                        filters[age_col] = selected_age
                        filter_types[age_col] = "select"
            
            # Standard/Class filter
            std_cols = find_matching_columns("standard") or find_matching_columns("class")
            if std_cols:
                std_col = std_cols[0]  # Use first matching column
                standards = ['All'] + sorted(df[std_col].astype(str).unique().tolist())
                selected_standard = filter_cols[2].selectbox("Standard/Class", standards)
                if selected_standard != 'All':
                    filters[std_col] = selected_standard
                    filter_types[std_col] = "select"
            
            # Division filter
            div_cols = find_matching_columns("division") or find_matching_columns("div")
            if div_cols:
                div_col = div_cols[0]  # Use first matching column
                divisions = ['All'] + sorted(df[div_col].astype(str).unique().tolist())
                selected_division = filter_cols[3].selectbox("Division", divisions)
                if selected_division != 'All':
                    filters[div_col] = selected_division
                    filter_types[div_col] = "select"
            
            # Apply filters
            filtered_df = df.copy()
            for column, value in filters.items():
                if column in filtered_df.columns:
                    filter_type = filter_types.get(column, "select")
                    
                    if filter_type == "range":
                        # Apply range filter
                        filtered_df = filtered_df[
                            (filtered_df[column] >= value[0]) & 
                            (filtered_df[column] <= value[1])
                        ]
                    else:
                        # Apply equality filter
                        filtered_df = filtered_df[filtered_df[column].astype(str) == str(value)]
            
            # Parent Name Filter (only for child forms)
            parent_forms_list = get_parent_forms(form_name)
            if parent_forms_list and 'parent_id' in filtered_df.columns:
                parent_form_name = parent_forms_list[0]
                parent_records = get_form_data(parent_form_name) if parent_form_name else []
                
                if parent_records:
                    # Create a mapping of display names to IDs
                    parent_options = {}
                    for record in parent_records:
                        # Try to find a suitable display name
                        display_name = None
                        for field in ['name', 'title', 'full_name', 'first_name']:
                            if field in record and record[field]:
                                display_name = str(record[field])
                                break
                        if not display_name:
                            display_name = f"ID: {record['id']}"
                        
                        parent_options[f"{display_name} (ID: {record['id']})"] = record['id']
                    
                    selected_parent = st.selectbox(
                        f"Filter by {parent_form_name}",
                        ["All"] + list(parent_options.keys()),
                        key=f"parent_select_{st.session_state.active_admin_tab}"
                    )
                    
                    if selected_parent != "All":
                        parent_id = parent_options[selected_parent]
                        filtered_df = filtered_df[filtered_df['parent_id'] == parent_id]
                        # Store parent context for relationship management
                        tab['parent_id'] = parent_id
                        tab['parent_form'] = parent_form_name
                    else:
                        # Clear parent context if "All" is selected
                        tab.pop('parent_id', None)
                        tab.pop('parent_form', None)
            
            # ========================================================= #
            # <<< --- START: NEW CHILD-TO-CHILD RELATIONSHIP CODE --- >>> #
            # ========================================================= #
            # This section only appears when a specific parent record has been selected from the filter above.
            if tab.get('parent_id') and tab.get('parent_form'):
                parent_id = tab['parent_id']
                parent_form = tab['parent_form']
                
                # Get all possible child forms for this parent type.
                all_child_forms = get_child_forms(parent_form)
                st.info(f"DEBUG: Found children for parent '{parent_form}': {all_child_forms}")
                
                if all_child_forms and len(all_child_forms) >= 2:
                    with st.expander("🔗 Establish Child-to-Child Relationships", expanded=False):
                        st.subheader(f"Relationships for {parent_form} (ID: {parent_id})")
                        st.info(f"Create relationships between different child forms of this parent (e.g., link a record from 'Teachers' to a record in 'Students').")
                        
                        # --- Relationship Creation UI ---
                        st.markdown("##### Create New Relationship")
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            source_form = st.selectbox("First Child Form", all_child_forms, key=f"source_form_{parent_id}")
                        with col2:
                            # The second form cannot be the same as the first one.
                            target_options = [f for f in all_child_forms if f != source_form]
                            if not target_options:
                                st.warning("You need at least two different child forms to create a relationship.")
                                target_form = None
                            else:
                                target_form = st.selectbox("Second Child Form", target_options, key=f"target_form_{parent_id}")
                        
                        if source_form and target_form:
                            # Get records for both forms that belong to the selected parent.
                            source_records = get_child_records(source_form, parent_id)
                            target_records = get_child_records(target_form, parent_id)
                            
                            if source_records and target_records:
                                # Helper to create a user-friendly display name for a record.
                                def get_display_name(record):
                                    for field in ['name', 'title', 'full_name', 'first_name', 'student_name', 'teacher_name']:
                                        if field in record and record[field]:
                                            return f"{record[field]} (ID: {record['id']})"
                                    return f"Record ID: {record['id']}"
                                
                                source_options = {get_display_name(r): r['id'] for r in source_records}
                                target_options = {get_display_name(r): r['id'] for r in target_records}
                                
                                rel_type = st.text_input("Relationship Type (e.g., Teaches, Advisor, Mentor)", key=f"rel_type_{parent_id}")
                                
                                col1, col2 = st.columns(2)
                                with col1:
                                    source_key = st.selectbox(f"Select a record from '{source_form}'", list(source_options.keys()))
                                with col2:
                                    target_key = st.selectbox(f"Select a record from '{target_form}'", list(target_options.keys()))
                                
                                if st.button("🔗 Create Relationship", use_container_width=True):
                                    if rel_type.strip():
                                        if create_child_relationship(
                                            parent_id,
                                            source_form, source_options[source_key],
                                            target_form, target_options[target_key],
                                            rel_type.strip()
                                        ):
                                            st.success("Relationship created successfully!")
                                            st.rerun()
                                        else:
                                            st.error("Failed to create relationship. It might already exist.")
                                    else:
                                        st.warning("Please specify a relationship type.")
                            else:
                                st.warning("Both selected forms must have at least one record associated with this parent to create a relationship.")

                        # --- Relationship Management UI ---
                        st.markdown("---")
                        st.subheader("Manage Existing Relationships")
                        relationships = get_child_relationships(parent_id)
                        
                        if relationships:
                            # Format for display in a DataFrame
                            rel_data = []
                            for rel in relationships:
                                rel_data.append({
                                    "ID": rel["id"],
                                    "From": f"{rel['child_form1']} (ID: {rel['record_id1']})",
                                    "Relationship": rel["relationship_type"],
                                    "To": f"{rel['child_form2']} (ID: {rel['record_id2']})",
                                    "Created": rel["created_at"].strftime("%Y-%m-%d %H:%M")
                                })
                            
                            rel_df = pd.DataFrame(rel_data)
                            st.dataframe(rel_df, hide_index=True, use_container_width=True)
                            
                            # --- Deletion UI ---
                            st.markdown("##### Delete Relationships")
                            to_delete_ids = st.multiselect("Select relationships to delete", rel_df['ID'].tolist())
                            
                            if st.button("🗑️ Delete Selected Relationships", type="primary"):
                                if delete_child_relationships(to_delete_ids):
                                    st.success(f"Deleted {len(to_delete_ids)} relationship(s).")
                                    st.rerun()
                                else:
                                    st.error("Deletion failed. Please try again.")
                        else:
                            st.info("No relationships have been created for this parent record yet.")
                            
                        # --- Visualization UI ---
                        if relationships:
                            st.markdown("---")
                            st.subheader("Relationship Visualization")
                            try:
                                import graphviz
                                dot = graphviz.Digraph(comment=f'Relationships for {parent_form} ID {parent_id}')
                                dot.attr('node', shape='box', style='rounded')

                                # Add a central parent node
                                dot.node(f"P_{parent_id}", f"{parent_form}\n(ID: {parent_id})", style='filled', fillcolor='lightblue')
                                
                                # Keep track of nodes to avoid duplicates and connect them to the parent
                                added_nodes = set()

                                for rel in relationships:
                                    # Define unique node IDs
                                    source_node_id = f"R_{rel['child_form1']}_{rel['record_id1']}"
                                    target_node_id = f"R_{rel['child_form2']}_{rel['record_id2']}"

                                    # Add nodes if not already present
                                    if source_node_id not in added_nodes:
                                        dot.node(source_node_id, f"{rel['child_form1']}\n(ID: {rel['record_id1']})")
                                        dot.edge(f"P_{parent_id}", source_node_id, style='dashed', arrowhead='none')
                                        added_nodes.add(source_node_id)
                                    
                                    if target_node_id not in added_nodes:
                                        dot.node(target_node_id, f"{rel['child_form2']}\n(ID: {rel['record_id2']})")
                                        dot.edge(f"P_{parent_id}", target_node_id, style='dashed', arrowhead='none')
                                        added_nodes.add(target_node_id)

                                    # Add the relationship edge
                                    dot.edge(source_node_id, target_node_id, label=rel['relationship_type'])

                                st.graphviz_chart(dot)

                            except ImportError:
                                st.warning("Please install the 'graphviz' library to see visualizations: `pip install graphviz`")
                            except Exception as e:
                                st.error(f"Could not generate visualization: {e}")

                else:
                    st.info("To establish relationships, the parent form must have at least two different child forms linked to it.")

            # ======================================================= #
            # <<< --- END: NEW CHILD-TO-CHILD RELATIONSHIP CODE --- >>> #
            # ======================================================= #

            # Display data
            st.subheader(f"Submission Data for {form_name}")
            
            # Add selection checkboxes for deletion
            filtered_df['Select'] = False
            edited_df = st.data_editor(
                filtered_df,
                column_config={
                    "Select": st.column_config.CheckboxColumn(required=True)
                },
                disabled=filtered_df.columns.drop('Select').tolist(),
                hide_index=True,
                use_container_width=True,
                key=f"data_editor_{st.session_state.active_admin_tab}"
            )
            
            # Get selected rows for deletion
            selected_rows = edited_df[edited_df.Select]
            
            # Data deletion section
            st.subheader("Data Management")
            
            if not selected_rows.empty:
                st.warning(f"Selected {len(selected_rows)} records for deletion")
                if st.button("Delete Selected Records", key=f"delete_selected_{st.session_state.active_admin_tab}"):
                    record_ids = selected_rows['id'].tolist()
                    if delete_records(form_name, record_ids):
                        st.success(f"Deleted {len(record_ids)} records successfully!")
                        # Refresh data
                        tab["data"] = get_form_data(form_name)
                        st.rerun()
                    else:
                        st.error("Failed to delete records")
            else:
                st.info("Select records using the checkboxes to enable deletion")
            
            # Show child records if this is a parent form
            child_forms = get_child_forms(form_name)
            if child_forms:
                with st.expander("Child Records"):
                    for child_form in child_forms:
                        # Get valid parent IDs from the filtered data
                        parent_ids = [int(row['id']) for row in filtered_df.to_dict('records') 
                                    if 'id' in row and pd.notna(row['id'])]
                        
                        if parent_ids:
                            try:
                                child_data = []
                                with get_connection() as conn:
                                    with conn.cursor() as cur:
                                        # Use parameterized query with ANY for array of parent IDs
                                        cur.execute(
                                            f"""
                                            SELECT * FROM "{child_form.replace(' ', '_').lower()}" 
                                            WHERE parent_id = ANY(%s)
                                            """,
                                            (parent_ids,)
                                        )
                                        columns = [desc[0] for desc in cur.description]
                                        child_data = [dict(zip(columns, row)) for row in cur.fetchall()]
                                
                                if child_data:
                                    child_df = pd.DataFrame(child_data)
                                    st.write(f"### {child_form}")
                                    st.dataframe(child_df)
                                else:
                                    st.info(f"No {child_form} records found for selected parents")
                            except Exception as e:
                                st.error(f"Error loading {child_form} records: {str(e)}")
                        else:
                            st.warning("No valid parent IDs found in current selection")
            
            # Show related records
            st.subheader("Related Records")
            parent_forms = get_parent_forms(form_name)
            if parent_forms:
                with st.expander("Parent Records"):
                    for parent_form in parent_forms:
                        parent_ids = [str(row.get('parent_id', '')) for row in filtered_df.to_dict('records') if row.get('parent_id')]
                        if parent_ids:
                            with get_connection() as conn:
                                with conn.cursor() as cur:
                                    cur.execute(
                                        f"SELECT * FROM {parent_form.replace(' ', '_').lower()} WHERE id IN ({','.join(parent_ids)})"
                                    )
                                    parent_records = cur.fetchall()
                                    if parent_records:
                                        parent_df = pd.DataFrame(parent_records)
                                        st.write(f"### {parent_form}")
                                        st.dataframe(parent_df)
                            
            # Add download button
            csv = filtered_df.drop(columns=['Select']).to_csv(index=False).encode('utf-8')
            st.download_button(
                "Download CSV",
                csv,
                f"{form_name.replace(' ', '_')}_data.csv",
                "text/csv",
                key=f'download-csv-{st.session_state.active_admin_tab}'
            )
    else:
        st.info("No analysis tabs open. Click '+ New' to start.")

elif st.session_state.page == "User Management":
    st.title("User Management")
    
    # Strict admin-only check
    if not st.session_state.user or "admin" not in st.session_state.user["permissions"]:
        st.error("🔒 Administrator privileges required")
        st.stop()
    
    # Create tabs for different functions
    tab1, tab2, tab3, tab4 = st.tabs(["Create Users", "Manage Users", "Password Reset","🩺 System Health"])
    
    with tab1:
        with st.form("create_user_form"):
            st.subheader("Create New User")
            new_username = st.text_input("Username", help="Must be unique")
            new_password = st.text_input("Password", type="password", help="Minimum 8 characters")
            new_role = st.selectbox("Role", ["admin", "editor", "viewer"])
            
            if st.form_submit_button("Create User"):
                if len(new_password) < 8:
                    st.error("Password must be at least 8 characters")
                elif not new_username:
                    st.error("Username is required")
                else:
                    if create_user(new_username, new_password, new_role):
                        st.success(f"User {new_username} created as {new_role}")
                        st.rerun()
                    else:
                        st.error("Username already exists or creation failed")

    with tab2:
        st.subheader("Existing Users")
        users = get_all_users()
        
        if not users:
            st.info("No users found in the system")
            st.stop()
            
        # Bulk actions section
        with st.expander("⚡ Bulk Actions", expanded=True):
            selected_users = st.multiselect(
                "Select users to manage",
                [u['username'] for u in users if u['username'] != st.session_state.user['username']],
                help="Select multiple users for bulk operations"
            )
            
            if selected_users:
                col1, col2 = st.columns(2)
                
                with col1:
                    new_role = st.selectbox(
                        "Set new role for selected users",
                        ["admin", "editor", "viewer"],
                        key="bulk_role"
                    )
                    if st.button("Update Roles", key="bulk_update"):
                        success = 0
                        for username in selected_users:
                            if update_user_role(username, new_role):
                                success += 1
                        st.success(f"Updated {success}/{len(selected_users)} users")
                        st.rerun()
                
                with col2:
                    st.write("")  # Spacer
                    if st.button("🗑️ Delete Selected", type="primary", key="bulk_delete"):
                        success = 0
                        for username in selected_users:
                            if delete_user(username):
                                success += 1
                        st.success(f"Deleted {success}/{len(selected_users)} users")
                        st.rerun()
        
        # Detailed user list
        st.markdown("---")
        st.subheader("Individual User Management")
        
        for user in users:
            # Skip current user
            if user['username'] == st.session_state.user['username']:
                continue
                
            with st.expander(f"👤 {user['username']} (Role: {user['role']})"):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    new_role = st.selectbox(
                        "Change role",
                        ["admin", "editor", "viewer"],
                        index=["admin", "editor", "viewer"].index(user['role']),
                        key=f"role_{user['id']}"
                    )
                    if st.button("Update Role", key=f"update_{user['id']}"):
                        if update_user_role(user['username'], new_role):
                            st.success("Role updated successfully")
                            st.rerun()
                
                with col2:
                    if st.button("Delete", key=f"delete_{user['id']}"):
                        if delete_user(user['username']):
                            st.success("User deleted successfully")
                            st.rerun()
                        else:
                            st.error("Deletion failed")

    with tab3:
        st.subheader("Password Reset Tool")
        with st.form("password_reset_form"):
            reset_username = st.selectbox(
                "Select User",
                [u['username'] for u in users],
                key="reset_select"
            )
            new_password = st.text_input("New Password", type="password", key="new_pw")
            confirm_password = st.text_input("Confirm Password", type="password", key="confirm_pw")
            
            if st.form_submit_button("Reset Password"):
                if len(new_password) < 8:
                    st.error("Password must be at least 8 characters")
                elif new_password != confirm_password:
                    st.error("Passwords don't match!")
                else:
                    if reset_user_password(reset_username, new_password):
                        st.success(f"Password reset for {reset_username}")
                    else:
                        st.error("Password reset failed")
    with tab4:
        st.subheader("Form Relationship Health Check")
        st.info("Use this tool to find and fix broken parent-child form links.")

        if st.button("Check Form Health"):
            health_report = get_foreign_key_info()
            st.session_state.health_report = health_report
        
        if 'health_report' in st.session_state:
            report = st.session_state.health_report
            if not report:
                st.warning("Could not generate a health report.")
            else:
                st.markdown("---")
                all_forms = [f['form_name'] for f in report]

                for item in report:
                    status = item['status']
                    form_name = item['form_name']

                    if status == 'OK':
                        st.success(f"✅ **{form_name}**: OK (Linked to **{item['linked_to']}**)")
                    elif status == 'Broken Link':
                        st.error(f"❌ **{form_name}**: Broken Link (Has `parent_id` but no official link)")
                        with st.form(key=f"fix_{item['sanitized_name']}"):
                            st.write(f"Repair link for **{form_name}**:")
                            # Filter out the child form itself from the list of potential parents
                            potential_parents = [f for f in all_forms if f != form_name]
                            selected_parent = st.selectbox("Select the correct parent form", potential_parents)
                            if st.form_submit_button("Repair Link"):
                                if repair_foreign_key(form_name, selected_parent):
                                    st.success(f"Link repaired! '{form_name}' is now a child of '{selected_parent}'. Please re-run the health check.")
                                    # Clear the report to force a refresh
                                    del st.session_state.health_report
                                    st.rerun()
                                else:
                                    st.error("Repair failed. Check the application logs for details.")

                    elif status == 'Parent':
                        st.info(f"ℹ️ **{form_name}**: Parent Form (or has no parent link)")
        st.subheader("System Health and Cleanup")
        st.info("This tool helps find and fix inconsistencies in your form data, such as 'orphan' form records where the metadata exists but the data table is missing.")

        if st.button("🔍 Scan for Orphan Records"):
            st.session_state.orphan_records = find_orphan_form_records()

        if 'orphan_records' in st.session_state:
            orphans = st.session_state.orphan_records
            if not orphans:
                st.success("✅ System scan complete. No orphan records found!")
            else:
                st.error(f"Found {len(orphans)} orphan record(s) that need cleanup.")
                
                df = pd.DataFrame(orphans)
                st.dataframe(df, use_container_width=True)

                st.markdown("---")
                st.subheader("Clean Up Orphan Records")
                
                orphans_to_delete = st.multiselect(
                    "Select orphan records to permanently delete",
                    options=[o['form_name'] for o in orphans]
                )

                if st.button("🗑️ Delete Selected Orphans", type="primary"):
                    deleted_count = 0
                    error_count = 0
                    for form_name in orphans_to_delete:
                        success, message = delete_form(form_name)
                        if success:
                            deleted_count += 1
                        else:
                            error_count += 1
                            st.warning(f"Could not delete '{form_name}': {message}")
                    
                    if deleted_count > 0:
                        st.success(f"Successfully deleted {deleted_count} orphan record(s).")
                    if error_count > 0:
                        st.error(f"Failed to delete {error_count} record(s). Check logs.")
                    
                    # Clear the cache and rerun to reflect changes
                    del st.session_state.orphan_records
                    st.rerun()
                    
elif st.session_state.page == "Update Forms":
    st.title("Form Management")
    check_access("update_forms")
    
    # Get all forms
    forms = get_all_forms()
    
    if not forms:
        st.warning("No forms available. Please create a form first.")
        st.stop()
    
    # Create tabs for Update and Delete functionality
    tab_update, tab_delete, tab_relationships = st.tabs(["Update Form", "Delete Form", "🔗 Manage Relationships"])
    
    with tab_update:
        # Form selection for updating
        selected_form = st.selectbox("Select Form to Update", forms, key="form_selector")
        
        if selected_form:
            # Load existing form data
            form_fields = get_form_fields(selected_form)
            
            if not form_fields:
                st.error("No fields found for selected form")
                st.stop()
            
            # Initialize session state for editing
            if ('edit_fields' not in st.session_state or 
                'current_form' not in st.session_state or
                st.session_state.current_form != selected_form):
                st.session_state.edit_fields = form_fields.copy()
                st.session_state.current_form = selected_form
                st.session_state.original_fields = form_fields.copy()
                st.session_state.removed_fields = []
            # Display editable fields
            st.subheader("Form Fields")
            st.write(f"Editing: {selected_form}")
            
            # Track fields to keep (those not marked for removal)
            fields_to_keep = []
                        # Display each field with edit and reorder options
            for i, field in enumerate(st.session_state.edit_fields):
                # Skip if this field was marked for removal
                if i in st.session_state.removed_fields:
                    continue
                
                # --- NEW: Added a column for reordering controls ---
                col_order, col1, col2, col3, col4 = st.columns([1, 3, 2, 2, 1])

                # Column for Up/Down arrow buttons
                with col_order:
                    # Move Up button
                    up_disabled = (i == 0)
                    if st.button("⬆️", key=f"up_{i}", disabled=up_disabled, help="Move field up"):
                        # Pop the item and insert it one position earlier
                        field_to_move = st.session_state.edit_fields.pop(i)
                        st.session_state.edit_fields.insert(i - 1, field_to_move)
                        st.rerun()

                    # Move Down button
                    down_disabled = (i == len(st.session_state.edit_fields) - 1)
                    if st.button("⬇️", key=f"down_{i}", disabled=down_disabled, help="Move field down"):
                        # Pop the item and insert it one position later
                        field_to_move = st.session_state.edit_fields.pop(i)
                        st.session_state.edit_fields.insert(i + 1, field_to_move)
                        st.rerun()

                # Existing columns for editing field properties
                with col1:
                    new_name = st.text_input(
                        "Field Name", 
                        value=field['name'],
                        key=f"name_{i}"
                    )
                    if new_name != field['name']:
                        st.session_state.edit_fields[i]['name'] = new_name
                
                with col2:
                    # Enhanced type selector with better grouping
                    type_options = {
                        "Text": ["VARCHAR(255)", "TEXT", "TEXTAREA", "EMAIL", "URL", "PHONE", "PASSWORD"],
                        "Numbers": ["INTEGER", "FLOAT", "RANGE"],
                        "Dates/Times": ["DATE", "DATETIME", "TIME"],
                        "Selections": ["SELECT", "RADIO", "CHECKBOX", "MULTISELECT"],
                        "Other": ["BOOLEAN", "COLOR", "FILE"]
                    }
                    
                    # Flatten for display while keeping original values
                    type_display = []
                    type_values = []
                    for group, options in type_options.items():
                        type_display.append(f"--- {group} ---")
                        type_values.append(None)  # Separator
                        type_display.extend(options)
                        type_values.extend(options)
                    
                    current_idx = type_values.index(field['type']) if field['type'] in type_values else 0
                    
                    new_type = st.selectbox(
                        "Field Type",
                        type_display,
                        index=current_idx,
                        format_func=lambda x: x if not x.startswith("---") else f"┈ {x.replace('---', '').strip()} ┈",
                        key=f"type_{i}"
                    )
                    
                    # Get actual value (not display value)
                    if new_type in type_values:
                        new_type_value = new_type
                    else:
                        # Handle group headers
                        new_type_value = field['type']
                    
                    if new_type_value != field['type']:
                        st.session_state.edit_fields[i]['type'] = new_type_value
                        # Clear options if type changes to non-option type
                        if new_type_value not in ["SELECT", "RADIO", "CHECKBOX", "MULTISELECT"]:
                            if 'options' in st.session_state.edit_fields[i]:
                                del st.session_state.edit_fields[i]['options']
                
                with col3:
                    # Show options for relevant field types
                    if field['type'] in ["SELECT", "RADIO", "CHECKBOX", "MULTISELECT"]:
                        current_options = field.get('options', [])
                        options_input = st.text_input(
                            "Options (comma separated)",
                            value=", ".join(current_options) if current_options else "",
                            key=f"options_{i}"
                        )
                        if options_input:
                            options = [opt.strip() for opt in options_input.split(",") if opt.strip()]
                            st.session_state.edit_fields[i]['options'] = options
                        else:
                            if 'options' in st.session_state.edit_fields[i]:
                                del st.session_state.edit_fields[i]['options']
                
                with col4:
                    if st.button("❌", key=f"remove_{i}"):
                        # Mark this field for removal
                        if 'removed_fields' not in st.session_state:
                            st.session_state.removed_fields = []
                        st.session_state.removed_fields.append(i)
                        st.rerun()
                
                fields_to_keep.append(field)
                        # Add new field
                        
            st.subheader("Add New Field")
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                new_field_name = st.text_input("New Field Name", key="new_field_name")
            with col2:
                new_field_type = st.selectbox(
                    "New Field Type",
                    [
                        "VARCHAR(255)", "INTEGER", "FLOAT", "DATE", "BOOLEAN", "TEXT", 
                        "PHONE", "TEXTAREA", "PASSWORD", "CHECKBOX", "RADIO", "SELECT", 
                        "DATETIME", "TIME", "MULTISELECT", "EMAIL", "URL", "COLOR", 
                        "FILE", "RANGE"
                    ],
                    key="new_field_type"
                )
            with col3:
                st.write("")  # Spacer
                if st.button("➕ Add Field"):
                    if new_field_name:
                        new_field = {"name": new_field_name, "type": new_field_type}
                        if new_field_type in ["SELECT", "RADIO", "CHECKBOX", "MULTISELECT"]:
                            new_field['options'] = []
                        # 1. The new field is added to the end of the list
                        st.session_state.edit_fields.append(new_field)
                        # 2. The page is re-run
                        st.rerun() 
                    else:
                        st.warning("Please enter a field name")
            # Display each field with edit options
            # for i, field in enumerate(st.session_state.edit_fields):
            #     # Skip if this field was marked for removal
            #     if i in st.session_state.removed_fields:
            #         continue
                    
            #     col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
                
            #     with col1:
            #         new_name = st.text_input(
            #             "Field Name", 
            #             value=field['name'],
            #             key=f"name_{i}"
            #         )
            #         if new_name != field['name']:
            #             st.session_state.edit_fields[i]['name'] = new_name
                
            #     with col2:
            #         # Enhanced type selector with better grouping
            #         type_options = {
            #             "Text": ["VARCHAR(255)", "TEXT", "TEXTAREA", "EMAIL", "URL", "PHONE", "PASSWORD"],
            #             "Numbers": ["INTEGER", "FLOAT", "RANGE"],
            #             "Dates/Times": ["DATE", "DATETIME", "TIME"],
            #             "Selections": ["SELECT", "RADIO", "CHECKBOX", "MULTISELECT"],
            #             "Other": ["BOOLEAN", "COLOR", "FILE"]
            #         }
                    
            #         # Flatten for display while keeping original values
            #         type_display = []
            #         type_values = []
            #         for group, options in type_options.items():
            #             type_display.append(f"--- {group} ---")
            #             type_values.append(None)  # Separator
            #             type_display.extend(options)
            #             type_values.extend(options)
                    
            #         current_idx = type_values.index(field['type']) if field['type'] in type_values else 0
                    
            #         new_type = st.selectbox(
            #             "Field Type",
            #             type_display,
            #             index=current_idx,
            #             format_func=lambda x: x if not x.startswith("---") else f"┈ {x.replace('---', '').strip()} ┈",
            #             key=f"type_{i}"
            #         )
                    
            #         # Get actual value (not display value)
            #         if new_type in type_values:
            #             new_type_value = new_type
            #         else:
            #             # Handle group headers
            #             new_type_value = field['type']
                    
            #         if new_type_value != field['type']:
            #             st.session_state.edit_fields[i]['type'] = new_type_value
            #             # Clear options if type changes to non-option type
            #             if new_type_value not in ["SELECT", "RADIO", "CHECKBOX", "MULTISELECT"]:
            #                 if 'options' in st.session_state.edit_fields[i]:
            #                     del st.session_state.edit_fields[i]['options']
                
            #     with col3:
            #         # Show options for relevant field types
            #         if field['type'] in ["SELECT", "RADIO", "CHECKBOX", "MULTISELECT"]:
            #             current_options = field.get('options', [])
            #             options_input = st.text_input(
            #                 "Options (comma separated)",
            #                 value=", ".join(current_options) if current_options else "",
            #                 key=f"options_{i}"
            #             )
            #             if options_input:
            #                 options = [opt.strip() for opt in options_input.split(",") if opt.strip()]
            #                 st.session_state.edit_fields[i]['options'] = options
            #             else:
            #                 if 'options' in st.session_state.edit_fields[i]:
            #                     del st.session_state.edit_fields[i]['options']
                
            #     with col4:
            #         if st.button("❌", key=f"remove_{i}"):
            #             # Mark this field for removal
            #             if 'removed_fields' not in st.session_state:
            #                 st.session_state.removed_fields = []
            #             st.session_state.removed_fields.append(i)
            #             st.rerun()
                
            #     fields_to_keep.append(field)
            
            # # Add new field
            # st.subheader("Add New Field")
            # col1, col2, col3 = st.columns([3, 2, 1])
            # with col1:
            #     new_field_name = st.text_input("New Field Name", key="new_field_name")
            # with col2:
            #     new_field_type = st.selectbox(
            #         "New Field Type",
            #         [
            #             "VARCHAR(255)", "INTEGER", "FLOAT", "DATE", "BOOLEAN", "TEXT", 
            #             "PHONE", "TEXTAREA", "PASSWORD", "CHECKBOX", "RADIO", "SELECT", 
            #             "DATETIME", "TIME", "MULTISELECT", "EMAIL", "URL", "COLOR", 
            #             "FILE", "RANGE"
            #         ],
            #         key="new_field_type"
            #     )
            # with col3:
            #     st.write("")  # Spacer
            #     if st.button("➕ Add Field"):
            #         if new_field_name:
            #             new_field = {"name": new_field_name, "type": new_field_type}
            #             if new_field_type in ["SELECT", "RADIO", "CHECKBOX", "MULTISELECT"]:
            #                 new_field['options'] = []
            #             st.session_state.edit_fields.append(new_field)
            #             st.rerun()
            #         else:
            #             st.warning("Please enter a field name")
            
            # Form actions
            st.markdown("---")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                if st.button("🔄 Reset Changes"):
                    # Clear all changes including removed fields
                    st.session_state.edit_fields = st.session_state.original_fields.copy()
                    st.session_state.removed_fields = []
                    st.rerun()
            
            with col2:
                if st.button("🔍 Preview Changes"):
                    st.subheader("Changes Preview")
                    
                    # Get current state of fields (excluding removed ones)
                    current_fields = [
                        field for i, field in enumerate(st.session_state.edit_fields) 
                        if i not in st.session_state.get('removed_fields', [])
                    ]
                    
                    # Find added fields
                    original_names = {f['name'] for f in st.session_state.original_fields}
                    current_names = {f['name'] for f in current_fields}
                    added_fields = [f for f in current_fields if f['name'] not in original_names]
                    
                    # Find removed fields
                    removed_fields = [f for f in st.session_state.original_fields if f['name'] not in current_names]
                    
                    # Find modified fields
                    modified_fields = []
                    original_field_map = {f['name']: f for f in st.session_state.original_fields}
                    for field in current_fields:
                        if field['name'] in original_field_map:
                            original_field = original_field_map[field['name']]
                            if field != original_field:
                                modified_fields.append({
                                    'name': field['name'],
                                    'original': original_field,
                                    'new': field
                                })
                    
                    # Display changes
                    if added_fields:
                        st.write("#### Fields to be added:")
                        st.json(added_fields)
                    
                    if removed_fields:
                        st.write("#### Fields to be removed:")
                        st.json(removed_fields)
                    
                    if modified_fields:
                        st.write("#### Fields to be modified:")
                        for change in modified_fields:
                            st.write(f"**{change['name']}**")
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write("Original:")
                                st.json(change['original'])
                            with col2:
                                st.write("New:")
                                st.json(change['new'])
                    
                    if not added_fields and not removed_fields and not modified_fields:
                        st.info("No changes detected")
            
            with col3:
                if st.button("💾 Save Changes", type="primary"):
                    try:
                        # Get final field list (excluding removed fields)
                        final_fields = [
                            field for i, field in enumerate(st.session_state.edit_fields)
                            if i not in st.session_state.get('removed_fields', [])
                        ]
                        
                        # Update form metadata
                        if not update_form_metadata(selected_form, final_fields):
                            st.error("Failed to update form metadata")
                            st.stop()
                        
                        # Update database table structure
                        if not update_dynamic_table(selected_form, final_fields, st.session_state.original_fields):
                            st.error("Failed to update table structure")
                            st.stop()
                        
                        # Regenerate form HTML
                        html_content = generate_html_form(selected_form, final_fields)
                        filepath = save_form_html(selected_form, html_content)
                        
                        st.success("Form updated successfully!")
                        st.balloons()
                        
                        # Update original fields reference
                        st.session_state.original_fields = final_fields.copy()
                        st.session_state.removed_fields = []
                        
                        # Show preview
                        st.subheader("Updated Form Preview")
                        st.components.v1.html(html_content, height=500, scrolling=True)
                    except Exception as e:
                        st.error(f"Error updating form: {str(e)}")
            # --- ADDED THIS NEW COLUMN AND LOGIC ---
            with col4:
                # This button enhances the *currently saved* state of the form
                if st.button("✨ Enhance with AI"):
                    st.info("Note: This will enhance the last saved version of the form's fields.")
                    with st.spinner(f"Sending '{selected_form}' to the AI for enhancement..."):
                        try:
                            # Use the 'original_fields' which represents the last saved state
                            fields_to_enhance = st.session_state.original_fields
                            fields_tuple = tuple(tuple(d.items()) for d in fields_to_enhance)
                            
                            # Call the LLM function
                            enhanced_html = generate_form_with_llama(selected_form, fields_tuple)
                            
                            if enhanced_html:
                                save_form_html(selected_form, enhanced_html)
                                st.success("AI enhancement complete!")
                                st.subheader("Enhanced Form Preview")
                                st.components.v1.html(enhanced_html, height=500, scrolling=True, key="enhanced_preview")
                            else:
                                st.error("AI enhancement failed to produce a result.")

                        except Exception as e:
                            st.error(f"AI enhancement failed: {e}")

            # Rest of the update form code remains the same...
            # [Previous update form implementation goes here]
    # THIS IS THE NEW, CORRECTED CODE
    with tab_delete:
        st.subheader("Delete Existing Form")
        
        forms_to_delete = get_all_forms()
        if not forms_to_delete:
            st.info("There are no forms to delete.")
        else:
            form_to_delete = st.selectbox(
                "Select a form to permanently delete",
                forms_to_delete,
                key="delete_form_select"
            )

            if form_to_delete:
                # Get the submission count, which could be an integer or an error string.
                submission_count = get_form_data_count(form_to_delete)

                # --- START OF THE CRITICAL FIX ---

                # First, check if the count is a valid integer.
                if isinstance(submission_count, int):
                    
                    # Display a clear warning about the number of submissions.
                    if submission_count > 0:
                        st.warning(f"This form currently has **{submission_count}** data submissions.")
                        st.error("⚠️ **DANGER:** Deleting this form will **permanently remove all associated data and submissions.** This action cannot be undone.")
                        export_confirm = st.checkbox(
                            "I understand that I should export the data first, as this deletion is irreversible.",
                            key=f"export_confirm_{form_to_delete}"
                        )
                    else:
                        st.info("This form has no data submissions.")
                        # If there are no submissions, the user doesn't need to confirm exporting.
                        export_confirm = True

                    delete_confirm = st.checkbox(
                        f"I confirm I want to **permanently delete** the form '{form_to_delete}' and all its data.",
                        key=f"delete_confirm_{form_to_delete}"
                    )
                    
                    # The delete button is only enabled if both checkboxes are checked.
                    if st.button("🗑️ Delete Form Permanently", type="primary", disabled=not (delete_confirm and export_confirm)):
                        # The delete_form function now returns a tuple (success, message)
                        success, message = delete_form(form_to_delete)
                        
                        if success:
                            st.success(message)
                            # Clean up session state to prevent errors
                            if 'current_form' in st.session_state and st.session_state.current_form == form_to_delete:
                                del st.session_state['current_form']
                                del st.session_state['edit_fields']
                            st.rerun()
                        else:
                            st.error(message)

                # If submission_count is NOT an integer, it's an error message from the database function.
                
                else:
                    # This block now handles the "orphan record" case.
                    st.error(f"Data Consistency Error: {submission_count}")
                    st.warning(f"The metadata for the form '{form_to_delete}' exists, but its data table does not. This is an orphan record.")
                    st.info("You can clean this up by deleting the form metadata below.")

                    # Allow deletion even if the table is missing.
                    delete_confirm = st.checkbox(
                        f"I confirm I want to **permanently delete** the orphan metadata for '{form_to_delete}'.",
                        key=f"delete_orphan_confirm_{form_to_delete}"
                    )
                    
                    if st.button("🗑️ Delete Orphan Record", type="primary", disabled=not delete_confirm):
                        # We can still use delete_form, as it's designed to handle this.
                        # It will find no children, delete permissions, and then fail to drop the table (which is fine),
                        # but it WILL delete the metadata from the 'forms' table.
                        success, message = delete_form(form_to_delete)
                        
                        if success:
                            st.success(f"Orphan record for '{form_to_delete}' was successfully removed.")
                            st.rerun()
                        else:
                            st.error(f"Failed to remove orphan record: {message}")
                
    with tab_relationships:
        st.subheader("Establish Parent-Child Form Links")
        st.info("Here you can define which forms are children of other forms. For example, a 'Students' form can be a child of a 'Schools' form.")

        all_forms = get_all_forms()
        if len(all_forms) < 2:
            st.warning("You need at least two forms to create a relationship.")
        else:
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### Select the Child Form")
                st.caption("This form will be linked under the parent.")
                child_form = st.selectbox(
                    "Child Form",
                    all_forms,
                    key="rel_child_select"
                )

            with col2:
                st.markdown("#### Select the Parent Form")
                st.caption("The child form will contain a reference to this form.")
                # A form cannot be its own parent, so we filter the list.
                parent_options = [f for f in all_forms if f != child_form]
                parent_form = st.selectbox(
                    "Parent Form",
                    parent_options,
                    key="rel_parent_select"
                )

            st.markdown("---")
            
            if child_form and parent_form:
                st.write(f"You are about to make **'{child_form}'** a child of **'{parent_form}'**.")
                st.warning("This will add a `parent_id` column to the child form's table, allowing you to link its records to records from the parent form. This action is generally not reversible through the UI.")

                if st.button("🔗 Create Link", use_container_width=True):
                    # Call the new database function
                    success, message = link_child_to_parent(child_form, parent_form)
                    
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
            else:
                st.info("Select both a child and a parent form to create a link.")

        # --- Display Current Relationships ---
        st.markdown("---")
        st.subheader("Current Form Hierarchy")

        if st.button("🔄 Refresh Hierarchy View"):
            # This button helps if things seem out of date
            pass

        try:
            # Use the get_foreign_key_info to visualize the hierarchy
            health_report = get_foreign_key_info()
            if not health_report:
                st.info("No parent-child relationships have been established yet.")
            else:
                import graphviz
                dot = graphviz.Digraph(comment='Form Hierarchy')
                dot.attr('node', shape='box', style='rounded,filled', fillcolor='lightblue')
                dot.attr(rankdir='TB', splines='ortho')

                all_report_forms = {item['form_name'] for item in health_report}
                
                # Add all forms as nodes first
                for form_name in all_report_forms:
                    dot.node(form_name, form_name)

                # Add edges for relationships
                for item in health_report:
                    if item['status'] == 'OK' and 'linked_to' in item:
                        parent = item['linked_to']
                        child = item['form_name']
                        dot.edge(parent, child)
                
                st.graphviz_chart(dot)

        except ImportError:
            st.warning("To see a visual hierarchy, please install graphviz: `pip install graphviz` and make sure you have the Graphviz system package installed.")
        except Exception as e:
            st.error(f"Could not generate hierarchy visualization: {e}")