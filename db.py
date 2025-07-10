# db.py
import psycopg2
import os
import streamlit as st
from dotenv import load_dotenv
import logging
import json
from typing import Dict, List, Optional, Union
import re
import datetime
from urllib.parse import urlparse
from streamlit.runtime.uploaded_file_manager import UploadedFile
# Set up logging
logging.basicConfig(level=logging.INFO) 
logger = logging.getLogger(__name__)

load_dotenv()

def get_connection():
    return psycopg2.connect(
        # dbname=os.getenv("DB_NAME", "form_generator"),
        # user=os.getenv("DB_USER", "postgres"),
        # password=os.getenv("DB_PASSWORD"),
        # host=os.getenv("DB_HOST", "localhost"),
        # port=os.getenv("DB_PORT", "5432")
        dbname=st.secrets["database"]["DB_NAME"],
        user=st.secrets["database"]["DB_USER"],
        password=st.secrets["database"]["DB_PASSWORD"],
        host=st.secrets["database"]["DB_HOST"],
        port=st.secrets["database"]["DB_PORT"]
    )

def initialize_database():
    """Initialize database with required tables"""
    commands = [
        """
        CREATE TABLE IF NOT EXISTS forms (
            id SERIAL PRIMARY KEY,
            form_name VARCHAR(255) UNIQUE NOT NULL,
            fields JSONB NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS form_permissions (
            id SERIAL PRIMARY KEY,
            form_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            can_view BOOLEAN DEFAULT FALSE,
            can_edit BOOLEAN DEFAULT FALSE,
            can_delete BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (form_id) REFERENCES forms(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(form_id, user_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS roles (
            name VARCHAR(50) PRIMARY KEY,
            permissions TEXT[] NOT NULL
        )
        """,
        # Insert default roles
        """
        INSERT INTO roles (name, permissions) 
        VALUES 
            ('admin', ARRAY['create', 'edit', 'delete', 'view_all', 'admin']),
            ('editor', ARRAY['create', 'edit', 'view']),
            ('viewer', ARRAY['view'])
        ON CONFLICT (name) DO NOTHING
        """,
        """
        CREATE TABLE IF NOT EXISTS child_relationships (
            id SERIAL PRIMARY KEY,
            parent_id INTEGER NOT NULL,
            child_form1 VARCHAR(255) NOT NULL,
            record_id1 INTEGER NOT NULL,
            child_form2 VARCHAR(255) NOT NULL,
            record_id2 INTEGER NOT NULL,
            relationship_type VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        ALTER TABLE forms ADD COLUMN IF NOT EXISTS share_token VARCHAR(255) UNIQUE;
        """
    ]
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                for command in commands:
                    cur.execute(command)
                conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        raise
# In db.py

# <<< --- ADD THIS NEW HELPER FUNCTION --- >>>
# It's best to place it right before get_parent_forms and get_child_forms

def get_form_name_from_table_name(table_name: str, cursor) -> Optional[str]:
    """
    Given a sanitized table name (e.g., 'schools_form'), queries the 'forms'
    metadata table to find the original, correct "pretty" name (e.g., 'Schools Form').
    """
    cursor.execute(
        "SELECT form_name FROM forms WHERE lower(trim(replace(form_name, ' ', '_'))) = %s",
        (table_name.lower().strip(),)
    )
    result = cursor.fetchone()
    return result[0] if result else None
def create_child_relationship(parent_id: int, child_form1: str, record_id1: int, child_form2: str, record_id2: int, relationship_type: str) -> bool:
    """Create a relationship between two child records under the same parent."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Insert the relationship, ignoring if it already exists to prevent errors.
                cur.execute("""
                    INSERT INTO child_relationships 
                    (parent_id, child_form1, record_id1, child_form2, record_id2, relationship_type)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (parent_id, child_form1, record_id1, child_form2, record_id2, relationship_type))
                conn.commit()
                # Return True if a row was inserted, False otherwise.
                return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Error creating child relationship: {str(e)}")
        conn.rollback()
        return False

def get_child_relationships(parent_id: int) -> List[Dict]:
    """Get all relationships for a specific parent record."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM child_relationships 
                    WHERE parent_id = %s
                    ORDER BY created_at DESC
                """, (parent_id,))
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"Error getting child relationships: {str(e)}")
        return []

def delete_child_relationships(relationship_ids: List[int]) -> bool:
    """Delete one or more relationships by their IDs."""
    if not relationship_ids:
        return False
        
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Use ANY(%s) for safe and efficient deletion of multiple rows.
                cur.execute(
                    "DELETE FROM child_relationships WHERE id = ANY(%s)",
                    (relationship_ids,)
                )
                conn.commit()
                return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Error deleting child relationships: {str(e)}")
        conn.rollback()
        return False

# <<< --- ADD THESE TWO NEW FUNCTIONS TO db.py --- >>>

def get_foreign_key_info() -> List[Dict]:
    """
    A diagnostic function to check the parent-child link status for all forms.
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Get all forms and their sanitized table names
                cur.execute("SELECT form_name, lower(replace(form_name, ' ', '_')) FROM forms")
                forms = {row[1]: row[0] for row in cur.fetchall()} # {sanitized_name: original_name}
                
                # Get all foreign key constraints in the public schema
                cur.execute("""
                    SELECT
                        tc.table_name,
                        ccu.table_name AS foreign_table_name
                    FROM
                        information_schema.table_constraints AS tc
                    JOIN information_schema.constraint_column_usage AS ccu
                        ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                """)
                # {child_table: parent_table}
                links = {row[0]: row[1] for row in cur.fetchall()}

                # Check if each table has a parent_id column
                cur.execute("""
                    SELECT table_name
                    FROM information_schema.columns
                    WHERE column_name = 'parent_id'
                """)
                tables_with_parent_id = {row[0] for row in cur.fetchall()}

                # Now, build the health report
                report = []
                for sanitized_name, original_name in forms.items():
                    info = {'form_name': original_name, 'sanitized_name': sanitized_name, 'status': 'Parent'}
                    if sanitized_name in tables_with_parent_id:
                        if sanitized_name in links:
                            parent_sanitized = links[sanitized_name]
                            info['status'] = 'OK'
                            info['linked_to'] = forms.get(parent_sanitized, parent_sanitized)
                        else:
                            info['status'] = 'Broken Link'
                            info['linked_to'] = 'None'
                    report.append(info)
                return report
    except Exception as e:
        logger.error(f"Error getting foreign key info: {e}")
        return []

def repair_foreign_key(child_form_name: str, parent_form_name: str) -> bool:
    """
    Retroactively creates a missing foreign key constraint.
    """
    child_table = child_form_name.replace(" ", "_").lower()
    parent_table = parent_form_name.replace(" ", "_").lower()
    constraint_name = f"fk_repaired_{child_table}_parent"

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Step 1: Drop existing constraint if it has a conflicting name (optional but safe)
                cur.execute(f"ALTER TABLE \"{child_table}\" DROP CONSTRAINT IF EXISTS {constraint_name}")

                # Step 2: Add the new, correct foreign key constraint
                cur.execute(f"""
                    ALTER TABLE "{child_table}"
                    ADD CONSTRAINT {constraint_name}
                    FOREIGN KEY (parent_id)
                    REFERENCES "{parent_table}"(id)
                    ON DELETE CASCADE
                """)
                conn.commit()
                logger.info(f"Successfully repaired foreign key for '{child_table}' to '{parent_table}'")
                return True
    except Exception as e:
        logger.error(f"Failed to repair FK for '{child_table}': {e}")
        conn.rollback()
        return False

# Ensure this function exists and is correct, it's used by the new UI
def get_child_records(child_form: str, parent_id: int) -> List[Dict]:
    """Get records from a child form with a specific parent ID."""
    table_name = child_form.replace(" ", "_").lower()
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'SELECT * FROM "{table_name}" WHERE parent_id = %s',
                    (parent_id,)
                )
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"Error getting child records: {str(e)}")
        return []

# ... (keep all your other existing functions in db.py)
def save_form_metadata(form_name, fields) -> int:
    """Save form metadata and return the form ID"""
    try:
        fields_json = json.dumps(fields)
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Insert and return the generated ID
                cur.execute(
                    "INSERT INTO forms (form_name, fields) VALUES (%s, %s) RETURNING id",
                    (form_name, fields_json)
                )
                result = cur.fetchone()
                if result:
                    form_id = result[0]
                    conn.commit()
                    return form_id
                else:
                    logger.error("No ID returned after INSERT")
                    return None
    except Exception as e:
        logger.error(f"Error saving form metadata for form '{form_name}': {str(e)}")
        return None
def debug_save_operation(form_name: str, data: dict):
    """Detailed debug information for save operations"""
    table_name = form_name.replace(" ", "_").lower()
    result = {
        "table_exists": False,
        "columns": None,
        "data_types": None,
        "constraints": None,
        "error": None
    }
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                # Check table existence
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = %s
                    )
                """, (table_name,))
                result["table_exists"] = cur.fetchone()[0]
                
                # Get column info
                cur.execute("""
                    SELECT column_name, data_type, is_nullable 
                    FROM information_schema.columns 
                    WHERE table_name = %s
                """, (table_name,))
                result["columns"] = cur.fetchall()
                
                # Get constraints
                cur.execute("""
                    SELECT conname, pg_get_constraintdef(oid) 
                    FROM pg_constraint 
                    WHERE conrelid = %s::regclass
                """, (table_name,))
                result["constraints"] = cur.fetchall()
                
                # Try a test insert
                test_data = {k: None for k in data.keys()}
                columns = [f'"{k}"' for k in test_data.keys()]
                placeholders = ', '.join(['%s'] * len(test_data))
                
                cur.execute(f"""
                    INSERT INTO "{table_name}" 
                    ({", ".join(columns)})
                    VALUES ({placeholders})
                    ON CONFLICT DO NOTHING
                """, list(test_data.values()))
                
            except Exception as e:
                result["error"] = str(e)
                conn.rollback()
            finally:
                conn.commit()
    
    return result
# Add this helper function in db.py
def is_empty_submission(data: dict) -> bool:
    """Check if form data is essentially empty"""
    for v in data.values():
        if isinstance(v, str) and v.strip():
            return False
        elif isinstance(v, (list, dict)) and v:
            return False
        elif v is not None and not isinstance(v, (str, list, dict)):
            return False
    return True
def save_form_data(form_name: str, form_data: dict) -> bool:
    table_name = form_name.replace(" ", "_").lower()
    
    # Enhanced data processing
    clean_data = {}
    for k, v in form_data.items():
        # Skip empty values
        if v in (None, "", [], {}):
            continue
            
        # Handle different data types
        if isinstance(v, list):
            # Convert list to PostgreSQL array string format
            clean_data[k.replace(" ", "_").lower()] = "{" + ",".join([str(item) for item in v]) + "}"
        elif isinstance(v, (datetime.date, datetime.time, datetime.datetime)):
            # Convert datetime objects to strings
            clean_data[k.replace(" ", "_").lower()] = v.isoformat()
        elif isinstance(v, bool):
            # Convert boolean to PostgreSQL compatible format
            clean_data[k.replace(" ", "_").lower()] = 'true' if v else 'false'
        else:
            clean_data[k.replace(" ", "_").lower()] = v
    
    if not clean_data:
        logger.warning("No valid data to save - skipping")
        return False
        
    # Remove 'id' field if present
    if 'id' in clean_data:
        del clean_data['id']
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Build dynamic SQL
                columns = [f'"{col}"' for col in clean_data.keys()]
                placeholders = ', '.join(['%s'] * len(clean_data))
                
                query = f"""
                    INSERT INTO "{table_name}" 
                    ({", ".join(columns)})
                    VALUES ({placeholders})
                """
                
                # Convert values to tuple for execution
                values = tuple(clean_data.values())
                cur.execute(query, values)
                conn.commit()
                return True
                
    except Exception as e:
        logger.error(f"Save failed: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
        return False

def delete_records(form_name: str, record_ids: List[int]) -> bool:
    """Delete multiple records from a form table"""
    table_name = form_name.replace(" ", "_").lower()
    if not record_ids:
        return False
        
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Use parameterized query to prevent SQL injection
                cur.execute(
                    f"DELETE FROM \"{table_name}\" WHERE id = ANY(%s)",
                    (record_ids,)
                )
                conn.commit()
                return True
    except Exception as e:
        logger.error(f"Error deleting records: {str(e)}")
        return False


def get_record(form_name: str, record_id: int) -> Optional[Dict]:
    """Get a single record by ID"""
    table_name = form_name.replace(" ", "_").lower()
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'SELECT * FROM "{table_name}" WHERE id = %s',
                    (record_id,)
                )
                columns = [desc[0] for desc in cur.description]
                row = cur.fetchone()
                return dict(zip(columns, row)) if row else None
    except Exception as e:
        logger.error(f"Error getting record: {str(e)}")
        return None

def get_all_forms():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT form_name FROM forms")
            return [row[0] for row in cur.fetchall()]
def validate_against_schema(form_name: str, data: dict) -> bool:
    """Validate data against database schema"""
    table_name = form_name.replace(" ", "_").lower()
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Get required columns
            cur.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = %s AND is_nullable = 'NO'
            """, (table_name,))
            required_columns = {row[0]: row[1] for row in cur.fetchall() if row[0] != 'id'}
            
            # Check required fields
            errors = []
            for col, col_type in required_columns.items():
                if col not in data or data[col] is None:
                    errors.append(f"Missing required field: {col}")
            
            if errors:
                st.error("\n".join(errors))
                return False
            return True

def inspect_table(form_name: str):
    """Inspect table schema"""
    table_name = form_name.replace(" ", "_").lower()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = %s
                ORDER BY ordinal_position
            """, (table_name,))
            return cur.fetchall()
def get_form_fields(form_name):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT fields FROM forms WHERE form_name = %s",
                (form_name,)
            )
            result = cur.fetchone()
            return result[0] if result else None

def verify_table_columns(form_name: str, fields: List[Dict]) -> bool:
    """Verify that all required columns exist in the table"""
    table_name = form_name.replace(" ", "_").lower()
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Get existing columns
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = %s
                """, (table_name,))
                existing_columns = {row[0] for row in cur.fetchall()}
                
                # Check required columns
                required_columns = {'id', 'created_at'}
                for field in fields:
                    field_name = field["name"].replace(" ", "_").lower()
                    required_columns.add(field_name)
                
                # Check for missing columns
                missing_columns = required_columns - existing_columns
                if missing_columns:
                    logger.warning(f"Missing columns in {table_name}: {missing_columns}")
                    return False
                
                return True
    except Exception as e:
        logger.error(f"Error verifying table columns: {e}")
        return False

def repair_table_columns(form_name: str, fields: List[Dict]) -> bool:
    """Add missing columns to a form table"""
    table_name = form_name.replace(" ", "_").lower()
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Get existing columns
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = %s
                """, (table_name,))
                existing_columns = {row[0] for row in cur.fetchall()}
                
                # Add missing columns
                for field in fields:
                    field_name = field["name"].replace(" ", "_").lower()
                    field_type = field["type"]
                    
                    if field_name not in existing_columns:
                        sql_type = get_sql_type(field_type)
                        try:
                            cur.execute(f"""
                                ALTER TABLE "{table_name}" 
                                ADD COLUMN "{field_name}" {sql_type}
                            """)
                            logger.info(f"Added column {field_name} ({sql_type}) to {table_name}")
                        except Exception as e:
                            logger.error(f"Failed to add column {field_name}: {e}")
                            continue
                
                conn.commit()
                return True
    except Exception as e:
        logger.error(f"Error repairing table columns: {e}")
        if conn:
            conn.rollback()
        return False
def get_form_data(form_name):
    sanitized_name = form_name.replace(" ", "_").lower()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {sanitized_name}")
            columns = [desc[0] for desc in cur.description]
            results = []
            for row in cur.fetchall():
                row_dict = {}
                for i, col in enumerate(columns):
                    # Handle array types
                    if isinstance(row[i], list):
                        row_dict[col] = list(row[i])
                    else:
                        row_dict[col] = row[i]
                results.append(row_dict)
            return results
# def get_form_data(form_name):
#     sanitized_name = form_name.replace(" ", "_").lower()
#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             cur.execute(f"SELECT * FROM {sanitized_name}")
#             columns = [desc[0] for desc in cur.description]
#             return [dict(zip(columns, row)) for row in cur.fetchall()]
        
#         # Add these functions to db.py

def add_parent_child_relationship(parent_form, child_form):
    """Add a parent-child relationship between forms"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Add parent_id column to child form if not exists
            sanitized_child = child_form.replace(" ", "_").lower()
            cur.execute(
                f"ALTER TABLE {sanitized_child} ADD COLUMN IF NOT EXISTS parent_id INTEGER"
            )
            # Add foreign key constraint if not exists
            try:
                cur.execute(
                    f"ALTER TABLE {sanitized_child} ADD CONSTRAINT fk_parent_{sanitized_child} "
                    f"FOREIGN KEY (parent_id) REFERENCES {parent_form.replace(' ', '_').lower()}(id)"
                )
            except Exception as e:
                logger.warning(f"Constraint may already exist: {str(e)}")
            conn.commit()

def get_child_forms(parent_form_name: str) -> List[str]:
    """
    Correctly finds all child forms for a given parent form by looking up
    the foreign key constraints that point to the parent's table.
    """
    # Sanitize the parent form name to match the table name in the database.
    parent_table_name = parent_form_name.replace(" ", "_").lower()
    child_forms = []

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # This query inspects the database's internal schema to find
                # tables (children) that have a foreign key referencing the parent table.
                # ccu.table_name is the table being referenced (the parent).
                # tc.table_name is the table that has the foreign key (the child).
                cur.execute("""
                    SELECT
                        tc.table_name AS child_table_name
                    FROM
                        information_schema.table_constraints AS tc
                    JOIN information_schema.constraint_column_usage AS ccu
                        ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
                    WHERE
                        tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name = %s
                """, (parent_table_name,))

                # This gives us a list of sanitized child table names (e.g., 'teachers_form').
                child_table_names = [row[0] for row in cur.fetchall()]

                if not child_table_names:
                    return []

                # Now, we must convert these database-friendly table names back into the
                # "pretty" form names that the UI uses (e.g., 'Teachers Form').
                # We use the provided helper function for this conversion.
                for table_name in child_table_names:
                    pretty_name = get_form_name_from_table_name(table_name, cur)
                    if pretty_name:
                        child_forms.append(pretty_name)

                return child_forms
    except Exception as e:
        logger.error(f"Error getting child forms for '{parent_form_name}': {str(e)}")
        return []
def get_parent_forms(child_form):
    """Get all parent forms for a given child form"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            sanitized_child = child_form.replace(" ", "_").lower()
            cur.execute("""
                SELECT ccu.table_name 
                FROM information_schema.table_constraints tc
                JOIN information_schema.constraint_column_usage ccu
                ON tc.constraint_name = ccu.constraint_name
                WHERE tc.table_name = %s
                AND tc.constraint_type = 'FOREIGN KEY'
                AND tc.constraint_name LIKE 'fk_parent_%%'
            """, (sanitized_child,))
            return [row[0].replace('_', ' ') for row in cur.fetchall()]
# In db.py, find and replace the existing delete_form function

def delete_form(form_name: str) -> tuple[bool, str]:
    """
    Safely deletes a form, its table, and related metadata.
    Checks for dependencies (like child forms) before deleting.
    Returns a tuple: (success_boolean, message_string).
    """
    sanitized_name = form_name.replace(" ", "_").lower()

    # --- SAFETY CHECK: Prevent deletion if this form is a parent to others ---
    try:
        children = get_child_forms(form_name)
        if children:
            message = f"Cannot delete '{form_name}' because it is a parent to other forms: {', '.join(children)}. Please delete the child forms first."
            logger.warning(message)
            return (False, message)
    except Exception as e:
        message = f"Could not verify child dependencies due to an error: {e}"
        logger.error(message)
        return (False, message)

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # --- Step 1: Get the form_id for cleanup ---
                cur.execute("SELECT id FROM forms WHERE form_name = %s", (form_name,))
                result = cur.fetchone()
                
                if not result:
                    # If metadata is gone but table might exist (orphan table)
                    cur.execute(f"DROP TABLE IF EXISTS \"{sanitized_name}\"")
                    conn.commit()
                    return (True, f"Form metadata for '{form_name}' was not found, but its data table (if it existed) was dropped.")
                
                form_id = result[0]

                # --- Step 2: Delete from dependent tables FIRST ---
                # Delete permissions associated with this form
                cur.execute("DELETE FROM form_permissions WHERE form_id = %s", (form_id,))
                
                # Delete any child-to-child relationships involving this form
                cur.execute("DELETE FROM child_relationships WHERE child_form1 = %s OR child_form2 = %s", (form_name, form_name))

                # --- Step 3: Delete the form metadata from the 'forms' table ---
                # This must happen before dropping the table if other tables (like form_permissions) have a FK to it.
                cur.execute("DELETE FROM forms WHERE id = %s", (form_id,))

                # --- Step 4: NOW it's safe to drop the data table ---
                cur.execute(f"DROP TABLE IF EXISTS \"{sanitized_name}\"")

                conn.commit()
                logger.info(f"Successfully deleted form '{form_name}', its table, and all related metadata.")
                return (True, f"Form '{form_name}' was deleted successfully!")

    except psycopg2.Error as e:
        # Catch specific database errors for better feedback
        conn.rollback()
        message = f"A database error occurred while deleting '{form_name}': {e}"
        logger.error(f"Error deleting form {form_name}: {str(e)}")
        return (False, message)
    except Exception as e:
        conn.rollback()
        message = f"An unexpected error occurred: {str(e)}"
        logger.error(message)
        return (False, message)        
            
def get_sql_type(field_type: str) -> str:
    """Map form field types to SQL types"""
    type_mapping = {
        "VARCHAR(255)": "VARCHAR(255)",
        "INTEGER": "INTEGER",
        "FLOAT": "FLOAT",
        "DATE": "DATE",
        "BOOLEAN": "BOOLEAN",
        "TEXT": "TEXT",
        "PHONE": "VARCHAR(20)",
        "TEXTAREA": "TEXT",
        "PASSWORD": "VARCHAR(255)",
        "CHECKBOX": "TEXT[]",  # Changed to array type
        "RADIO": "VARCHAR(255)",
        "SELECT": "VARCHAR(255)",
        "DATETIME": "TIMESTAMP",
        "TIME": "TIME",
        "MULTISELECT": "TEXT[]",  # Changed to array type
        "EMAIL": "VARCHAR(255)",
        "URL": "VARCHAR(255)",
        "COLOR": "VARCHAR(7)",
        "FILE": "BYTEA",
        "RANGE": "INTEGER"
    }
    return type_mapping.get(field_type.upper(), "VARCHAR(255)")
# Add these functions to db.py
def create_user(username: str, password_hash: str, role: str) -> bool:
    """Create a new user in the database"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                    (username, password_hash, role)
                )
                conn.commit()
                return True
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        return False
def get_user(username: str) -> Dict:
    """Get user by username"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, password_hash, role FROM users WHERE username = %s",
                (username,)
            )
            result = cur.fetchone()
            if result:
                return {
                    "id": result[0],
                    "username": result[1],
                    "password_hash": result[2],
                    "role": result[3]
                }
            return None

def set_form_permission(form_id: int, user_id: int, can_view: bool, can_edit: bool, can_delete: bool) -> bool:
    """Set permissions for a user on a specific form"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO form_permissions (form_id, user_id, can_view, can_edit, can_delete)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (form_id, user_id) DO UPDATE
                    SET can_view = EXCLUDED.can_view,
                        can_edit = EXCLUDED.can_edit,
                        can_delete = EXCLUDED.can_delete
                    """,
                    (form_id, user_id, can_view, can_edit, can_delete)
                )
                conn.commit()
                return True
    except Exception as e:
        logger.error(f"Error setting form permissions: {str(e)}")
        return False

def get_form_permissions(form_id: int, user_id: int) -> Dict:
    """Get permissions for a user on a specific form"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT can_view, can_edit, can_delete 
                FROM form_permissions 
                WHERE form_id = %s AND user_id = %s
                """,
                (form_id, user_id)
            )
            result = cur.fetchone()
            if result:
                return {
                    "can_view": result[0],
                    "can_edit": result[1],
                    "can_delete": result[2]
                }
            return None
        
def get_all_users() -> List[Dict[str, any]]:
    """Get all users from the database"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, role, created_at FROM users ORDER BY created_at DESC"
            )
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
        
def initialize_default_users():
    """Create default users if they don't exist"""
    default_users = [
        ("admin", "admin123", "admin"),
        ("editor", "editor123", "editor"),
        ("viewer", "viewer123", "viewer")
    ]
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            for username, password, role in default_users:
                # Check if user exists
                cur.execute("SELECT 1 FROM users WHERE username = %s", (username,))
                if not cur.fetchone():
                    # Insert new user
                    cur.execute(
                        "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                        (username, password, role)
                    )
            conn.commit()


def is_username_available(username: str) -> bool:
    """Check if username is available"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM users WHERE username = %s",
                (username,))
            return cur.fetchone() is None

def register_user(username: str, password_hash: str, role: str = "viewer") -> bool:
    """Register a new user with default viewer role"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                    (username, password_hash, role))
                conn.commit()
                return True
                
    except Exception as e:
        logger.error(f"Error registering user: {str(e)}")
        return False
# In db.py
# In your authentication utils (add at the top of db.py)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.security import DEFAULT_PBKDF2_ITERATIONS

# Force consistent hashing parameters
HASH_METHOD = 'pbkdf2:sha256'  # Using PBKDF2 instead of scrypt for compatibility
HASH_ITERATIONS = DEFAULT_PBKDF2_ITERATIONS  # Default is 600,000

def get_password_hash(password):
    """Generate consistent password hashes"""
    return generate_password_hash(
        password,
        method=HASH_METHOD,
        salt_length=16
    )
def register_user(username: str, password: str, role: str = "viewer") -> bool:
    """Register user with PROPERLY HASHED password"""
    try:
        password_hash = generate_password_hash(password)  # This creates the hash
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                    (username, password_hash, role)  # Store the HASHED version
                )
                conn.commit()
                return True
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return False
    
# Temporary function - run once then remove
def migrate_passwords():
    """Convert plaintext passwords to hashes"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Find users with plaintext passwords
            cur.execute("""
                SELECT id, password_hash FROM users 
                WHERE password_hash NOT LIKE 'pbkdf2:sha256:%'
            """)
            for user_id, plaintext in cur.fetchall():
                hashed = generate_password_hash(plaintext)
                cur.execute("""
                    UPDATE users SET password_hash = %s 
                    WHERE id = %s
                """, (hashed, user_id))
            conn.commit()
    st.success("Migrated all passwords to hashed format")


            
def is_properly_hashed(password_hash: str) -> bool:
    """Check if password is hashed"""
    return password_hash.startswith('pbkdf2:sha256:')

def validate_all_passwords():
    """Safety check for plaintext passwords"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT username FROM users WHERE password_hash NOT LIKE 'pbkdf2:sha256:%'")
            if bad_users := cur.fetchall():
                st.error(f"Plaintext passwords found for: {bad_users}")
                return False
    return True
def migrate_hashes():
    """Convert all hashes to consistent format"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Get all users
            cur.execute("SELECT id, username, password_hash FROM users")
            for user_id, username, current_hash in cur.fetchall():
                if current_hash.startswith('scrypt:'):
                    # Get the actual password (temporary - remove after migration)
                    password = input(f"Enter password for {username}: ")
                    new_hash = get_password_hash(password)
                    cur.execute(
                        "UPDATE users SET password_hash = %s WHERE id = %s",
                        (new_hash, user_id)
                    )
            conn.commit()
    st.success("Password hash migration complete")

# Call this once with caution (requires knowing existing passwords)
def update_user_role(username: str, new_role: str) -> bool:
    """Update a user's role"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET role = %s WHERE username = %s",
                    (new_role, username)
                )
                conn.commit()
                return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Role update failed: {str(e)}")
        return False

def delete_user(username: str) -> bool:
    """Permanently delete a user"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM users WHERE username = %s",
                    (username,)
                )
                conn.commit()
                return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Delete failed: {str(e)}")
        return False
def reset_user_password(username: str, new_password: str) -> bool:
    """Reset password with proper hashing"""
    try:
        password_hash = generate_password_hash(new_password)
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET password_hash = %s WHERE username = %s",
                    (password_hash, username))
                conn.commit()
                return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Password reset error: {str(e)}")
        return False

def create_dynamic_table(form_name: str, fields: List[Dict]) -> bool:
    """Create a new table for form data with dynamic schema"""
    try:
        table_name = form_name.replace(" ", "_").lower()
        
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Start with basic columns
                columns = [
                    "id SERIAL PRIMARY KEY",
                    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                ]
                
                # Add form fields with appropriate data types
                for field in fields:
                    field_name = field["name"].replace(" ", "_").lower()
                    sql_type = get_sql_type(field["type"])
                    
                    # Handle special types
                    if field["type"] == "MULTISELECT":
                        columns.append(f'"{field_name}" TEXT[]')
                    elif field["type"] == "CHECKBOX":
                        columns.append(f'"{field_name}" BOOLEAN[]')
                    else:
                        columns.append(f'"{field_name}" {sql_type}')
                
                # Create table - using triple quotes without f-string
                create_table_sql = '''
                    CREATE TABLE IF NOT EXISTS "{0}" (
                        {1}
                    )
                '''.format(table_name, ',\n'.join(columns))
                
                cur.execute(create_table_sql)
                
                # Add constraints for required fields
                for field in fields:
                    if field.get("required"):
                        field_name = field["name"].replace(" ", "_").lower()
                        try:
                            alter_sql = '''
                                ALTER TABLE "{0}" 
                                ALTER COLUMN "{1}" SET NOT NULL
                            '''.format(table_name, field_name)
                            cur.execute(alter_sql)
                        except Exception as e:
                            logger.warning(f"Could not set NOT NULL on {field_name}: {e}")
                            continue
                
                conn.commit()
                return True
                
    except Exception as e:
        logger.error(f"Error creating table: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
        return False
def update_form_metadata(form_name: str, fields: List[Dict]) -> bool:
    """Update an existing form's metadata in the database"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE forms 
                    SET fields = %s 
                    WHERE form_name = %s
                """, (json.dumps(fields), form_name))
                conn.commit()
                return True
    except Exception as e:
        print(f"Error updating form metadata: {e}")
        return False


def update_dynamic_table(form_name: str, new_fields: List[Dict], old_fields: List[Dict]) -> bool:
    """Update an existing form's table structure, ensuring all columns are lowercase."""
    try:
        table_name = form_name.replace(" ", "_").lower()
        
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Get current columns
                cur.execute(f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = %s
                """, (table_name,))
                existing_columns = {row[0] for row in cur.fetchall()}
                
                # --- Normalize all field names to lowercase for comparison ---
                old_field_names = {f['name'].replace(" ", "_").lower() for f in old_fields}
                new_field_map = {f['name'].replace(" ", "_").lower(): f for f in new_fields}

                # Columns to add
                fields_to_add = [
                    field for name, field in new_field_map.items() 
                    if name not in old_field_names
                ]
                
                # Columns to remove
                fields_to_remove_names = old_field_names - set(new_field_map.keys())
                
                # Columns to modify (type changes)
                fields_to_modify = []
                old_field_map_lower = {f['name'].replace(" ", "_").lower(): f for f in old_fields}
                for new_name_lower, new_field in new_field_map.items():
                    old_field = old_field_map_lower.get(new_name_lower)
                    if old_field and old_field['type'] != new_field['type']:
                        fields_to_modify.append(new_field)
                
                # Apply changes
                for field in fields_to_add:
                    # --- ALWAYS use lowercase for the column name ---
                    col_name = field['name'].replace(" ", "_").lower()
                    sql_type = get_sql_type(field['type'])
                    cur.execute(f"""
                        ALTER TABLE "{table_name}" 
                        ADD COLUMN "{col_name}" {sql_type}
                    """)
                
                for field_name_lower in fields_to_remove_names:
                    if field_name_lower in existing_columns and field_name_lower != 'id':
                        cur.execute(f"""
                            ALTER TABLE "{table_name}" 
                            DROP COLUMN "{field_name_lower}"
                        """)
                
                for field in fields_to_modify:
                    # --- ALWAYS use lowercase for the column name ---
                    col_name = field['name'].replace(" ", "_").lower()
                    sql_type = get_sql_type(field['type'])
                    cur.execute(f"""
                        ALTER TABLE "{table_name}" 
                        ALTER COLUMN "{col_name}" TYPE {sql_type}
                        USING "{col_name}"::text::{sql_type}
                    """)
                
                conn.commit()
                return True
    except Exception as e:
        print(f"Error updating table structure: {e}")
        conn.rollback() # Add rollback on error
        return False    
def check_table_exists(table_name: str) -> bool:
    """Check if a table exists in the database"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = %s
                    );
                """, (table_name,))
                return cur.fetchone()[0]
    except Exception as e:
        print(f"Error checking table existence: {e}")
        return False
    
import re
from urllib.parse import urlparse

def is_valid_url(url: str) -> bool:
    """Validate URL format with comprehensive checks"""
    if not url or not isinstance(url, str):
        return False
    
    # Basic pattern check
    url_pattern = re.compile(
        r'^(https?|ftp)://'  # http:// or https:// or ftp://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|'  # IPv4
        r'\[?[A-F0-9]*:[A-F0-9:]+\]?)'  # IPv6
        r'(?::\d+)?'  # port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    if not re.match(url_pattern, url):
        return False
    
    # Additional validation using urllib
    try:
        result = urlparse(url)
        if not all([result.scheme, result.netloc]):
            return False
        return True
    except ValueError:
        return False
    
def synchronize_form_table(form_name: str) -> bool:
    """Ensure database table matches form field definitions"""
    table_name = form_name.replace(" ", "_").lower()
    fields = get_form_fields(form_name)
    
    if not fields:
        return False

    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                # Get existing columns
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = %s
                """, (table_name,))
                existing_columns = {row[0].lower() for row in cur.fetchall()}
                
                # Add missing columns
                for field in fields:
                    col_name = field['name'].replace(" ", "_").lower()
                    sql_type = get_sql_type(field['type'])
                    
                    if col_name not in existing_columns:
                        cur.execute(f"""
                            ALTER TABLE "{table_name}" 
                            ADD COLUMN "{col_name}" {sql_type}
                        """)
                        logger.info(f"Added column {col_name} to {table_name}")
                
                conn.commit()
                return True
                
            except Exception as e:
                logger.error(f"Schema sync failed for {table_name}: {str(e)}")
                conn.rollback()
                return False
            
def ensure_parent_columns(form_name: str):
    """Ensure child tables have proper parent_id columns"""
    table_name = form_name.replace(" ", "_").lower()
    parent_forms = get_parent_forms(form_name)
    
    if not parent_forms:
        return True

    parent_form = parent_forms[0]
    parent_table = parent_form.replace(" ", "_").lower()

    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                # Add parent_id column if missing
                cur.execute(f"""
                    ALTER TABLE "{table_name}" 
                    ADD COLUMN IF NOT EXISTS parent_id INTEGER
                """)
                
                # Add foreign key constraint if missing
                cur.execute(f"""
                    ALTER TABLE "{table_name}" 
                    ADD CONSTRAINT fk_{table_name}_parent 
                    FOREIGN KEY (parent_id) REFERENCES "{parent_table}"(id)
                    ON DELETE CASCADE
                """)
                conn.commit()
                return True
            except Exception as e:
                logger.warning(f"Parent column setup: {str(e)}")
                conn.rollback()
                return False
def record_exists(form_name: str, record_id: int) -> bool:
    """Check if a record exists in the specified form table"""
    table_name = form_name.replace(" ", "_").lower()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT EXISTS(
                    SELECT 1 FROM "{table_name}" WHERE id = %s
                )
            """, (record_id,))
            return cur.fetchone()[0]
def get_form_data_count(form_name: str) -> Union[int, str]:
    """
    Enhanced version with better error handling
    Returns either the count or an error message
    """
    table_name = form_name.replace(" ", "_").lower()
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # First check if table exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = %s
                    )
                """, (table_name,))
                if not cur.fetchone()[0]:
                    return f"Table {table_name} does not exist"
                
                # Count records
                cur.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                return cur.fetchone()[0]
                
    except Exception as e:
        logger.error(f"Error counting records in {table_name}: {str(e)}")
        return f"Error: {str(e)}"
    
def get_parent_records(parent_form: str) -> List[Dict]:
    """Get all parent records with their display names"""
    table_name = parent_form.replace(" ", "_").lower()
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # First try to find a name column
                cur.execute(f"""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = %s 
                    AND column_name IN ('name', 'title', 'full_name', 'first_name')
                    LIMIT 1
                """, (table_name,))
                name_column = cur.fetchone()
                display_col = name_column[0] if name_column else 'id'
                
                # Get all parent records
                cur.execute(f"""
                    SELECT id, {display_col} FROM "{table_name}"
                    ORDER BY {display_col}
                """)
                return [{'id': row[0], 'display': str(row[1])} for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"Error getting parent records: {str(e)}")
        return []

def get_child_records_with_parent(child_form: str, parent_id: int = None) -> List[Dict]:
    """Get child records with optional parent filter"""
    table_name = child_form.replace(" ", "_").lower()
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                if parent_id:
                    cur.execute(f"""
                        SELECT * FROM "{table_name}" 
                        WHERE parent_id = %s
                        ORDER BY id
                    """, (parent_id,))
                else:
                    cur.execute(f"""
                        SELECT * FROM "{table_name}"
                        ORDER BY id
                    """)
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"Error getting child records: {str(e)}")
        return []
    

def dump_all_foreign_keys() -> List[Dict]:
    """
    A raw diagnostic tool to dump all foreign key relationships
    as the database sees them in its internal schema.
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # This query pulls the raw, unfiltered list of all foreign keys.
                query = """
                SELECT
                    tc.constraint_name,
                    tc.table_name      AS child_table,
                    kcu.column_name    AS child_column,
                    ccu.table_name     AS parent_table,
                    ccu.column_name    AS parent_column
                FROM
                    information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = ccu.table_schema
                WHERE
                    tc.constraint_type = 'FOREIGN KEY';
                """
                cur.execute(query)
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"Error dumping foreign keys: {e}")
        return [{"error": str(e)}]
    
# In db.py

# <<< --- ADD THIS NEW FUNCTION TO THE END OF db.py --- >>>
def fix_form_name_discrepancies() -> List[str]:
    """
    Finds and corrects discrepancies between the 'forms' metadata table
    and the actual table names in the database schema.
    This is often caused by pluralization (e.g., 'school' vs 'schools').
    """
    corrections_log = []
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Get all actual table names from the database schema
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                """)
                # Store as a set of sanitized names for easy lookup
                actual_tables = {row[0].lower().strip() for row in cur.fetchall()}

                # Get all form names from our metadata table
                cur.execute("SELECT id, form_name FROM forms")
                forms_metadata = cur.fetchall()

                for form_id, form_name in forms_metadata:
                    sanitized_meta_name = form_name.replace(" ", "_").lower().strip()
                    
                    # If the sanitized name from our metadata doesn't exist as a real table...
                    if sanitized_meta_name not in actual_tables:
                        # Try to find a match by adding/removing 's'
                        possible_match_plural = sanitized_meta_name + 's'
                        possible_match_singular = sanitized_meta_name.rstrip('s')

                        actual_match = None
                        if possible_match_plural in actual_tables:
                            actual_match = possible_match_plural
                        elif possible_match_singular in actual_tables:
                            actual_match = possible_match_singular

                        if actual_match:
                            # We found the real table! Let's correct our metadata.
                            # Convert the real table name back to a "pretty" name.
                            corrected_pretty_name = actual_match.replace("_", " ").strip().title()
                            
                            cur.execute("UPDATE forms SET form_name = %s WHERE id = %s", (corrected_pretty_name, form_id))
                            log_msg = f"Corrected '{form_name}' to '{corrected_pretty_name}' (table: {actual_match})"
                            corrections_log.append(log_msg)
                            logger.info(log_msg)
                        else:
                            corrections_log.append(f"WARNING: No matching table found for form '{form_name}'.")
                conn.commit()
        return corrections_log
    except Exception as e:
        logger.error(f"Error during name discrepancy fix: {e}")
        conn.rollback()
        return [f"ERROR: {e}"]
# Add this new function at the end of db.py

def find_orphan_form_records() -> List[Dict[str, str]]:
    """
    Compares the 'forms' metadata table against the actual database schema
    to find forms that exist in metadata but have no corresponding data table.
    Returns a list of orphan forms.
    """
    orphans = []
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Get all form names from the metadata table
                cur.execute("SELECT form_name FROM forms")
                metadata_forms = {row[0] for row in cur.fetchall()}

                # Get all actual table names from the database schema
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                """)
                # Sanitize the real table names for comparison
                actual_tables = {
                    get_form_name_from_table_name(row[0], cur) 
                    for row in cur.fetchall()
                }
                # Filter out None values in case of conversion failure
                actual_tables = {name for name in actual_tables if name}

                # Find metadata forms that don't have a corresponding real table
                # This logic is a bit tricky. We need to check if the metadata_form's
                # sanitized name exists in the list of real tables.
                
                # Let's re-do this logic more simply.
                cur.execute("SELECT form_name FROM forms")
                metadata_forms = cur.fetchall()

                for (form_name,) in metadata_forms:
                    sanitized_name = form_name.replace(" ", "_").lower()
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = %s
                        )
                    """, (sanitized_name,))
                    if not cur.fetchone()[0]:
                        orphans.append({
                            "form_name": form_name,
                            "reason": "Data table not found."
                        })
        return orphans
    except Exception as e:
        logger.error(f"Error finding orphan form records: {e}")
        return [{"error": str(e)}]
    
# In db.py, add this new function

def link_child_to_parent(child_form_name: str, parent_form_name: str) -> tuple[bool, str]:
    """
    Establishes a parent-child relationship by adding a 'parent_id' column and
    a foreign key constraint to the child form's table.
    Returns a tuple (success_boolean, message_string).
    """
    child_table = child_form_name.replace(" ", "_").lower()
    parent_table = parent_form_name.replace(" ", "_").lower()
    constraint_name = f"fk_{child_table}_parent_{parent_table}"

    if child_table == parent_table:
        return (False, "A form cannot be a parent to itself.")

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # --- Step 1: Add parent_id column to the child table if it doesn't exist ---
                # This is safe to run even if the column is already there.
                cur.execute(f"""
                    ALTER TABLE "{child_table}"
                    ADD COLUMN IF NOT EXISTS parent_id INTEGER;
                """)
                logger.info(f"Ensured 'parent_id' column exists in '{child_table}'.")

                # --- Step 2: Add the foreign key constraint ---
                # This will fail if the constraint already exists, which is caught by the exception.
                cur.execute(f"""
                    ALTER TABLE "{child_table}"
                    ADD CONSTRAINT "{constraint_name}"
                    FOREIGN KEY (parent_id) REFERENCES "{parent_table}"(id)
                    ON DELETE SET NULL;
                """)
                # ON DELETE SET NULL is safer than CASCADE for this operation.
                # It means if a parent is deleted, the child's parent_id becomes NULL instead of deleting the child record.
                
                conn.commit()
                message = f"Successfully linked '{child_form_name}' as a child to '{parent_form_name}'."
                logger.info(message)
                return (True, message)

    except psycopg2.Error as e:
        # Catch specific database errors for clear feedback
        conn.rollback()
        # Check if the error is "constraint already exists"
        if "already exists" in str(e):
            message = f"Relationship already exists between '{child_form_name}' and '{parent_form_name}'."
            logger.warning(message)
            return (False, message)
        
        message = f"A database error occurred: {e}"
        logger.error(message)
        return (False, message)
    except Exception as e:
        conn.rollback()
        message = f"An unexpected error occurred: {e}"
        logger.error(message)
        return (False, message)
    
def set_form_share_token(form_name: str, token: str) -> bool:
    """Set share token for a form"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE forms SET share_token = %s WHERE form_name = %s",
                    (token, form_name)
                )
                conn.commit()
                return True
    except Exception as e:
        logger.error(f"Error setting share token: {str(e)}")
        return False

def get_form_by_token(token: str) -> Optional[Dict]:
    """Get form metadata by share token"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT form_name, fields FROM forms WHERE share_token = %s",
                (token,)
            )
            result = cur.fetchone()
            if result:
                return {
                    "form_name": result[0],
                    "fields": result[1]
                }
            return None

def get_share_token(form_name: str) -> Optional[str]:
    """Get existing share token for a form"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT share_token FROM forms WHERE form_name = %s",
                (form_name,)
            )
            result = cur.fetchone()
            return result[0] if result else None