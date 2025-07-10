# form_utils.py
import ollama
import json
import os
import logging
from dotenv import load_dotenv
# in app.py
load_dotenv(override=True)
# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
def get_navigation_css():
    """Returns CSS to fix navigation arrow styling"""
    return """
    <style>
    /* Fix for navigation arrows */
    .nav-arrow {
        display: inline-block;
        margin: 0 5px;
    }
    .nav-arrow::after {
        content: ">";
        font-family: inherit;
    }
    </style>
    """
# In form_utils.py

# This function will become our primary, instant form generator.
def generate_html_form(form_name: str, fields: list) -> str:
    """
    Instantly generates a functional Bootstrap 5 HTML form from a list of fields
    without calling an LLM. This should be the default method.
    """
    # Start with Bootstrap CDN and a container
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{form_name}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
    <div class="container mt-4">
        <h2>{form_name}</h2>
        <form action="#" method="POST">
    """

    # Loop through fields and generate the correct HTML input
    for field in fields:
        field_name = field.get("name", "unnamed_field")
        # Sanitize name for HTML attributes
        sanitized_name = field_name.replace(" ", "_").lower()
        field_type = field.get("type", "TEXT")
        options = field.get("options", [])
        
        html += f'        <div class="mb-3">\n'
        html += f'            <label for="{sanitized_name}" class="form-label">{field_name}</label>\n'

        if field_type == "TEXTAREA":
            html += f'            <textarea class="form-control" id="{sanitized_name}" name="{sanitized_name}" rows="3" required></textarea>\n'
        elif field_type == "SELECT":
            html += f'            <select class="form-select" id="{sanitized_name}" name="{sanitized_name}" required>\n'
            for option in options:
                html += f'                <option value="{option}">{option}</option>\n'
            html += f'            </select>\n'
        elif field_type == "RADIO":
            for i, option in enumerate(options):
                html += f'''
            <div class="form-check">
                <input class="form-check-input" type="radio" name="{sanitized_name}" id="{sanitized_name}_{i}" value="{option}" required>
                <label class="form-check-label" for="{sanitized_name}_{i}">
                    {option}
                </label>
            </div>'''
        elif field_type == "MULTISELECT":
            html += f'            <select class="form-select" id="{sanitized_name}" name="{sanitized_name}" multiple required>\n'
            for option in options:
                html += f'                <option value="{option}">{option}</option>\n'
            html += f'            </select>\n'
        elif field_type == "CHECKBOX":
            # For a single boolean checkbox
            html += f'''
            <div class="form-check">
                <input class="form-check-input" type="checkbox" id="{sanitized_name}" name="{sanitized_name}" value="true">
                <label class="form-check-label" for="{sanitized_name}">Yes/No</label>
            </div>'''
        elif field_type == "PHONE":
            html += f'            <input type="tel" class="form-control" id="{sanitized_name}" name="{sanitized_name}" pattern="[0-9]{{10,15}}" title="10-15 digit phone number" required>\n'
        elif field_type == "EMAIL":
            html += f'            <input type="email" class="form-control" id="{sanitized_name}" name="{sanitized_name}" required>\n'
        elif field_type == "DATE":
            html += f'            <input type="date" class="form-control" id="{sanitized_name}" name="{sanitized_name}" required>\n'
        elif field_type == "DATETIME":
            html += f'            <input type="datetime-local" class="form-control" id="{sanitized_name}" name="{sanitized_name}" required>\n'
        elif field_type == "TIME":
            html += f'            <input type="time" class="form-control" id="{sanitized_name}" name="{sanitized_name}" required>\n'
        elif field_type == "INTEGER" or field_type == "FLOAT" or field_type == "RANGE":
            html += f'            <input type="number" class="form-control" id="{sanitized_name}" name="{sanitized_name}" required>\n'
        elif field_type == "PASSWORD":
            html += f'            <input type="password" class="form-control" id="{sanitized_name}" name="{sanitized_name}" required>\n'
        else: # Default to text input
            html += f'            <input type="text" class="form-control" id="{sanitized_name}" name="{sanitized_name}" required>\n'
        
        html += f'        </div>\n'

    # Add submit button and close tags
    html += """
            <button type="submit" class="btn btn-primary">Submit</button>
        </form>
    </div>
</body>
</html>
    """
    return html
def generate_form_with_llama(form_name, fields):
    confirmation_message = f"Request received: Enhancing form '{form_name}' with AI (LLM)..."
    print(confirmation_message) # For immediate console feedback
    logger.info(confirmation_message) # For structured logging
    try:
        nav_css = get_navigation_css()
        # Create field specifications string
        field_specs = "\n".join(
            [f"- {field['name']} ({field['type']})" for field in fields]
        )
        
        prompt = f"""
        Create an HTML form for '{form_name}' with the following fields:
        {field_specs}
        
        Requirements:
        1. Use Bootstrap 5 for styling
        2. Wrap each field in a div with class 'mb-3'
        3. Use appropriate input types based on data types:
            - VARCHAR(255)/TEXT: text input or textarea
            - INTEGER/FLOAT: number input
            - DATE: date input
            - BOOLEAN: checkbox
            - PHONE: tel input with pattern validation
        4. Add 'required' attribute to all fields
        5. Include a submit button with class 'btn btn-primary'
        6. Add form labels with field names
        7. Use field names for input names and IDs
        8. For phone fields, add pattern="[0-9]{{10,15}}" and title="10-15 digit phone number"
        9. For navigation elements, use:
            <span class="nav-arrow"></span> 
            instead of Material Icons
        10. Include this CSS:
        {nav_css}
        """
        
        response = ollama.generate(
            model='llama2',
            prompt=prompt,
            options={'temperature': 0.2}
        )
        
        return response['response']
    except Exception as e:
        logger.error(f"Error generating form: {str(e)}")
        return generate_html_form(form_name, fields)

def generate_fallback_form(fields):
    """Generate a simple form as fallback when LLAMA fails"""
    form_html = get_navigation_css() +'<form>\n'
    for field in fields:
        field_name = field["name"]
        field_type = field["type"]
        if field_type in ["RADIO", "SELECT", "CHECKBOX", "MULTISELECT"]:
            options = field.get("options", [])
        input_type = "text"
        if "INT" in field_type:
            input_type = "number"
        elif "FLOAT" in field_type:
            input_type = "number"
        elif "DATE" in field_type:
            input_type = "date"
        elif "BOOLEAN" in field_type:
            input_type = "checkbox"
        elif "PHONE" in field_type:
            input_type = "tel"
        
        form_html += f'  <div class="mb-3">\n'
        form_html += f'    <label for="{field_name}" class="form-label">{field_name}</label>\n'
        
        if field_type == "PHONE":
            form_html += f'    <input type="tel" class="form-control" id="{field_name}" name="{field_name}" pattern="[0-9]{{10,15}}" title="10-15 digit phone number">\n'
        else:
            form_html += f'    <input type="{input_type}" class="form-control" id="{field_name}" name="{field_name}">\n'
        
        form_html += '  </div>\n\n'
    
    form_html += '  <button type="submit" class="btn btn-primary">Submit</button>\n'
    form_html += '</form>'
    return form_html
# Corrected function in form_utils.py

def generate_embed_code(form_name: str, token: str, base_url: str) -> str:
    """Generate HTML embed code for a form"""
    # Use the corrected URL structure (base_url + ?token=...)
    embed_url = f"{base_url}?token={token}"
    return f"""
    <iframe 
        src="{embed_url}" 
        title="{form_name}"
        width="100%" 
        height="600px"
        frameborder="0"
        style="border: 1px solid #ddd; border-radius: 5px;"
    ></iframe>
    """
def save_form_html(form_name, html_content):
    try:
        # Ensure navigation CSS exists in the content
        if 'nav-arrow' not in html_content:
            html_content = get_navigation_css() + html_content
        os.makedirs("generated_forms", exist_ok=True)
        filename = f"{form_name.replace(' ', '_').lower()}.html"
        filepath = os.path.join("generated_forms", filename)
        
        # Add Bootstrap CDN if missing
        if '<link href="https://cdn.jsdelivr.net/npm/bootstrap' not in html_content:
            bootstrap_cdn = """
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            """
            html_content = bootstrap_cdn + html_content
        
        with open(filepath, "w") as f:
            f.write(html_content)
        
        return filepath
    except Exception as e:
        logger.error(f"Error saving form HTML: {str(e)}")
        return None
def get_html_input(field):
        field_type = field.get("type", "TEXT")
        field_name = field["name"]
        required = "required" if field.get("required") else ""
        
        if field_type == "TEXTAREA":
            return f'<textarea class="form-control" name="{field_name}" {required}></textarea>'
        
        elif field_type == "PASSWORD":
            return f'<input type="password" class="form-control" name="{field_name}" {required}>'
        
        elif field_type == "CHECKBOX_GROUP":
            options = field.get("options", "").split(',')
            html = ""
            for opt in options:
                html += f'''
                <div class="form-check">
                    <input class="form-check-input" type="checkbox" name="{field_name}[]" value="{opt}">
                    <label class="form-check-label">{opt}</label>
                </div>
                '''
            return html
        
        # Add similar blocks for other field types...
        
        # Default text input
        return f'<input type="text" class="form-control" name="{field_name}" {required}>'
