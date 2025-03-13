from typing import Any

from starlette.responses import HTMLResponse

from lihil.problems import DetailBase
from lihil.utils.phasing import encode_json

problem_ui_default_parameters: dict[str, Any] = {
    "dom_id": "#problem-ui",
    "deepLinking": True,
    "showExtensions": True,
}


swagger_ui_default_parameters: dict[str, Any] = {
    "dom_id": "#swagger-ui",
    "layout": "BaseLayout",
    "deepLinking": True,
    "showExtensions": True,
    "showCommonExtensions": True,
}


def get_swagger_ui_html(
    *,
    openapi_url: str,
    title: str,
    swagger_js_url: str = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.2.0/swagger-ui-bundle.js",
    swagger_css_url: str = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.2.0/swagger-ui.css",
    swagger_favicon_url: str = "",
    oauth2_redirect_url: str | None = None,
    init_oauth: dict[str, Any] | None = None,
    swagger_ui_parameters: dict[str, Any] | None = None,
) -> HTMLResponse:
    current_swagger_ui_parameters = swagger_ui_default_parameters.copy()
    if swagger_ui_parameters:
        current_swagger_ui_parameters.update(swagger_ui_parameters)

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <link type="text/css" rel="stylesheet" href="{swagger_css_url}">
    <link rel="shortcut icon" href="{swagger_favicon_url}">
    <title>{title}</title>
    </head>
    <body>
    <div id="swagger-ui">
    </div>
    <script src="{swagger_js_url}"></script>
    <!-- `SwaggerUIBundle` is now available on the page -->
    <script>
    const ui = SwaggerUIBundle({{
        url: '{openapi_url}',
    """

    for key, value in current_swagger_ui_parameters.items():
        html += f"{encode_json(key).decode()}: {encode_json(value).decode()},\n"

    if oauth2_redirect_url:
        html += f"oauth2RedirectUrl: window.location.origin + '{oauth2_redirect_url}',"

    html += """
    presets: [
        SwaggerUIBundle.presets.apis,
        SwaggerUIBundle.SwaggerUIStandalonePreset
        ],
    })"""

    if init_oauth:
        html += f"""
        ui.initOAuth({encode_json(init_oauth)})
        """

    html += """
    </script>
    </body>
    </html>
    """
    return HTMLResponse(html)


def get_swagger_ui_oauth2_redirect_html() -> HTMLResponse:
    # copied from https://github.com/swagger-api/swagger-ui/blob/v4.14.0/dist/oauth2-redirect.html
    html = """
    <!doctype html>
    <html lang="en-US">
    <head>
        <title>Swagger UI: OAuth2 Redirect</title>
    </head>
    <body>
    <script>
        'use strict';
        function run () {
            var oauth2 = window.opener.swaggerUIRedirectOauth2;
            var sentState = oauth2.state;
            var redirectUrl = oauth2.redirectUrl;
            var isValid, qp, arr;

            if (/code|token|error/.test(window.location.hash)) {
                qp = window.location.hash.substring(1).replace('?', '&');
            } else {
                qp = location.search.substring(1);
            }

            arr = qp.split("&");
            arr.forEach(function (v,i,_arr) { _arr[i] = '"' + v.replace('=', '":"') + '"';});
            qp = qp ? JSON.parse('{' + arr.join() + '}',
                    function (key, value) {
                        return key === "" ? value : decodeURIComponent(value);
                    }
            ) : {};

            isValid = qp.state === sentState;

            if ((
              oauth2.auth.schema.get("flow") === "accessCode" ||
              oauth2.auth.schema.get("flow") === "authorizationCode" ||
              oauth2.auth.schema.get("flow") === "authorization_code"
            ) && !oauth2.auth.code) {
                if (!isValid) {
                    oauth2.errCb({
                        authId: oauth2.auth.name,
                        source: "auth",
                        level: "warning",
                        message: "Authorization may be unsafe, passed state was changed in server. The passed state wasn't returned from auth server."
                    });
                }

                if (qp.code) {
                    delete oauth2.state;
                    oauth2.auth.code = qp.code;
                    oauth2.callback({auth: oauth2.auth, redirectUrl: redirectUrl});
                } else {
                    let oauthErrorMsg;
                    if (qp.error) {
                        oauthErrorMsg = "["+qp.error+"]: " +
                            (qp.error_description ? qp.error_description+ ". " : "no accessCode received from the server. ") +
                            (qp.error_uri ? "More info: "+qp.error_uri : "");
                    }

                    oauth2.errCb({
                        authId: oauth2.auth.name,
                        source: "auth",
                        level: "error",
                        message: oauthErrorMsg || "[Authorization failed]: no accessCode received from the server."
                    });
                }
            } else {
                oauth2.callback({auth: oauth2.auth, token: qp, isValid: isValid, redirectUrl: redirectUrl});
            }
            window.close();
        }

        if (document.readyState !== 'loading') {
            run();
        } else {
            document.addEventListener('DOMContentLoaded', function () {
                run();
            });
        }
    </script>
    </body>
    </html>
        """
    return HTMLResponse(content=html)


def get_problem_ui_html(
    *,
    title: str,
    problems: list[type[DetailBase[Any]]],
    problem_js_url: str = "https://cdn.jsdelivr.net/npm/jquery@3.6.0/dist/jquery.min.js",
    bootstrap_css_url: str = "https://cdn.jsdelivr.net/npm/bootstrap@5.2.3/dist/css/bootstrap.min.css",
    bootstrap_js_url: str = "https://cdn.jsdelivr.net/npm/bootstrap@5.2.3/dist/js/bootstrap.bundle.min.js",
    problem_favicon_url: str = "",
    problem_ui_parameters: dict[str, Any] | None = None,
) -> HTMLResponse:
    current_problem_ui_parameters = problem_ui_default_parameters.copy()
    if problem_ui_parameters:
        current_problem_ui_parameters.update(problem_ui_parameters)

    # Convert problems to JSON-serializable format
    problem_examples: list[dict[str, Any]] = []
    for problem_class in problems:
        example = problem_class.__json_example__()
        problem_examples.append(
            {
                "type": example["type_"],
                "title": example["title"],
                "status": example["status"],
                "detail": "Example detail for this error type",
                "instance": "Example instance for this error type",
                "description": problem_class.__doc__
                or f"{problem_class.__name__} error",
                "className": problem_class.__name__,
            }
        )

    # Encode problem examples as JSON
    problems_json = encode_json(problem_examples).decode()

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <link type="text/css" rel="stylesheet" href="{bootstrap_css_url}">
        <link rel="shortcut icon" href="{problem_favicon_url}">
        <title>{title} - Problem Details</title>
        <style>
            body {{
                padding: 20px;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            }}
            .problem-card {{
                margin-bottom: 20px;
                border-radius: 8px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }}
            .problem-card .card-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .status-badge {{
                font-size: 14px;
                padding: 5px 10px;
                border-radius: 20px;
            }}
            .search-container {{
                margin-bottom: 30px;
            }}
            .no-results {{
                text-align: center;
                padding: 40px;
                color: #666;
            }}
            pre {{
                background-color: #f8f9fa;
                padding: 15px;
                border-radius: 5px;
            }}
            .problem-type {{
                font-family: monospace;
                word-break: break-all;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="mb-4">{title} - Problem Details</h1>
            <p class="lead">
                This page documents all possible error responses that can be returned by the API.
                Each error follows the <a href="https://www.rfc-editor.org/rfc/rfc9457.html" target="_blank">RFC 9457</a> 
                Problem Details specification.
            </p>
            
            <div class="search-container">
                <div class="row">
                    <div class="col-md-6">
                        <div class="input-group mb-3">
                            <input type="text" id="search-input" class="form-control" placeholder="Search problems...">
                            <button class="btn btn-outline-secondary" type="button" id="clear-search">Clear</button>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <select id="status-filter" class="form-select">
                            <option value="">All Status Codes</option>
                        </select>
                    </div>
                </div>
            </div>
            
            <div id="problem-ui">
                <div id="problems-container"></div>
                <div id="no-results" class="no-results" style="display: none;">
                    <h3>No matching problem details found</h3>
                    <p>Try adjusting your search criteria</p>
                </div>
            </div>
        </div>
        
        <script src="{problem_js_url}"></script>
        <script src="{bootstrap_js_url}"></script>
        <script>
            // Store all problems
            const allProblems = {problems_json};
            
            // Function to render problems
            function renderProblems(problems) {{
                const container = document.getElementById('problems-container');
                container.innerHTML = '';
                
                if (problems.length === 0) {{
                    document.getElementById('no-results').style.display = 'block';
                    return;
                }}
                
                document.getElementById('no-results').style.display = 'none';
                
                problems.forEach(problem => {{
                    const statusColorClass = getStatusColorClass(problem.status);
                    
                    const problemCard = document.createElement('div');
                    problemCard.className = 'card problem-card';
                    
                    problemCard.innerHTML = `
                        <div class="card-header">
                            <h5 class="mb-0">${{problem.className}}</h5>
                            <span class="badge ${{statusColorClass}} status-badge">Status: ${{problem.status}}</span>
                        </div>
                        <div class="card-body">
                            <p class="problem-type"><strong>Type:</strong> ${{problem.type}}</p>
                            <p><strong>Description:</strong> ${{problem.title || 'No title available'}}</p>
                            <p><strong>Example:</strong></p>
                            <pre>{{
  "type": "${{problem.type}}",
  "title": "${{problem.title}}",
  "status": ${{problem.status}},
  "detail": "${{problem.detail}}",
  "instance": "${{problem.instance}}"
}}</pre>
                        </div>
                    `;
                    
                    container.appendChild(problemCard);
                }});
            }}
            
            // Function to get status code color
            function getStatusColorClass(status) {{
                if (status >= 200 && status < 300) return 'bg-success';
                if (status >= 300 && status < 400) return 'bg-info';
                if (status >= 400 && status < 500) return 'bg-warning';
                if (status >= 500) return 'bg-danger';
                return 'bg-secondary';
            }}
            
            // Function to filter problems
            function filterProblems() {{
                const searchTerm = document.getElementById('search-input').value.toLowerCase();
                const statusFilter = document.getElementById('status-filter').value;
                
                const filtered = allProblems.filter(problem => {{
                    const matchesSearch = 
                        problem.type.toLowerCase().includes(searchTerm) || 
                        problem.title.toLowerCase().includes(searchTerm) ||
                        (problem.description && problem.description.toLowerCase().includes(searchTerm));
                    
                    const matchesStatus = !statusFilter || problem.status.toString() === statusFilter;
                    
                    return matchesSearch && matchesStatus;
                }});
                
                renderProblems(filtered);
                
                // Update URL with search parameters
                const url = new URL(window.location);
                if (searchTerm) {{
                    url.searchParams.set('search', searchTerm);
                }} else {{
                    url.searchParams.delete('search');
                }}
                
                if (statusFilter) {{
                    url.searchParams.set('status', statusFilter);
                }} else {{
                    url.searchParams.delete('status');
                }}
                
                window.history.replaceState({{}}, '', url);
            }}
            
            // Initialize the UI
            document.addEventListener('DOMContentLoaded', function() {{
                // Populate status filter dropdown
                const statusFilter = document.getElementById('status-filter');
                const statusCodes = [...new Set(allProblems.map(p => p.status))].sort((a, b) => a - b);
                
                statusCodes.forEach(code => {{
                    const option = document.createElement('option');
                    option.value = code;
                    option.textContent = code;
                    statusFilter.appendChild(option);
                }});
                
                // Set up event listeners
                document.getElementById('search-input').addEventListener('input', filterProblems);
                document.getElementById('status-filter').addEventListener('change', filterProblems);
                document.getElementById('clear-search').addEventListener('click', function() {{
                    document.getElementById('search-input').value = '';
                    document.getElementById('status-filter').value = '';
                    filterProblems();
                }});
                
                // Check for URL parameters
                const urlParams = new URLSearchParams(window.location.search);
                const searchParam = urlParams.get('search');
                const statusParam = urlParams.get('status');
                
                if (searchParam) {{
                    document.getElementById('search-input').value = searchParam;
                }}
                
                if (statusParam) {{
                    document.getElementById('status-filter').value = statusParam;
                }}
                
                // Initial render
                filterProblems();
            }});
        </script>
    </body>
    </html>
    """
    return HTMLResponse(html)
