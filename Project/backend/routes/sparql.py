"""SPARQL query routes."""

from flask import Blueprint, request, jsonify

from services.domain.sparql_service import sparql_service

sparql_bp = Blueprint('sparql', __name__, url_prefix='/api/sparql')


@sparql_bp.route('', methods=['POST'])
def sparql_query():
    """Execute SPARQL queries on the ontology."""
    try:
        data = request.get_json()
        if not data or 'query' not in data:
            return jsonify({'error': 'No SPARQL query provided'}), 400

        query = data.get('query').strip()
        result = sparql_service.execute_query(query)

        if 'error' in result and result['error']:
            status_code = 408 if 'timeout' in result['error'].lower() else 400
            return jsonify(result), status_code

        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': f'Query error: {str(e)}'}), 400


@sparql_bp.route('/examples', methods=['GET'])
def get_sparql_examples():
    """Get example SPARQL queries."""
    examples = sparql_service.get_examples()
    return jsonify(examples), 200
