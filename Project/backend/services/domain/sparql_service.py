"""
SPARQL Query Service
Handles ontology loading and SPARQL query execution
"""

import os
from rdflib import Graph


class SPARQLService:
    """Service for executing SPARQL queries against the ontology"""
    
    def __init__(self):
        self.graph = None
        self.ontology_path = os.path.join(
            os.path.dirname(__file__),
            '..',
            'ontology',
            'OS_ontology_exported.owl'
        )
    
    def load_ontology(self):
        """Load ontology into memory for SPARQL queries"""
        try:
            self.graph = Graph()
            if os.path.exists(self.ontology_path):
                self.graph.parse(self.ontology_path, format='turtle')
                print(f"[SPARQL] Ontology loaded: {len(self.graph)} triples")
                return True
            else:
                print(f"[WARNING] Ontology file not found at {self.ontology_path}")
                return False
        except Exception as e:
            print(f"[ERROR] Failed to load ontology: {e}")
            return False
    
    def execute_query(self, query_string):
        """
        Execute SPARQL query and return formatted results
        
        Args:
            query_string: SPARQL query string
            
        Returns:
            dict: Results and metadata
        """
        if self.graph is None:
            return {
                'error': 'Ontology not loaded',
                'results': [],
                'count': 0
            }
        
        try:
            # Validate query complexity
            if query_string.upper().count('?') > 20:
                return {
                    'error': 'Query too complex (too many variables). Please simplify.',
                    'results': [],
                    'count': 0
                }
            
            # Execute query
            results = self.graph.query(query_string)
            
            # Format results
            formatted = []
            if results:
                for row in results:
                    formatted.append({
                        str(col): str(val) for col, val in zip(results.vars, row)
                    })
            
            return {
                'results': formatted,
                'count': len(formatted),
                'variables': [str(var) for var in results.vars] if hasattr(results, 'vars') else [],
                'info': 'Query completed successfully'
            }
        except TimeoutError as e:
            return {
                'error': f'Query timeout: {str(e)}. Try a simpler query or add LIMIT clause.',
                'results': [],
                'count': 0
            }
        except Exception as e:
            error_msg = str(e)
            if 'Timeout' in error_msg:
                error_msg = 'Query is taking too long. Try adding LIMIT 50 or a simpler query.'
            
            return {
                'error': f'Query error: {error_msg}',
                'results': [],
                'count': 0
            }
    
    @staticmethod
    def get_examples():
        """Get example SPARQL queries optimized for the ontology"""
        return {
            'count_resources': {
                'title': 'Count All Resources',
                'query': '''PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?type (COUNT(*) AS ?count)
WHERE {
  ?resource a ?type .
}
GROUP BY ?type
ORDER BY DESC(?count)'''
            },
            'all_lessons': {
                'title': 'List All Lessons',
                'query': '''PREFIX solo: <http://example.org/solo-education-ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?lesson ?title
WHERE {
  ?lesson a solo:Lesson ;
          rdfs:label ?title .
}
ORDER BY ?title'''
            },
            'all_questions': {
                'title': 'List All Questions',
                'query': '''PREFIX solo: <http://example.org/solo-education-ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?question ?title
WHERE {
  ?question a solo:MultipleChoiceQuestion ;
            rdfs:label ?title .
}
ORDER BY ?question'''
            },
            'lesson_sections': {
                'title': 'Sections by Lesson',
                'query': '''PREFIX solo: <http://example.org/solo-education-ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?lesson ?lessonTitle ?section ?sectionTitle (COUNT(?lo) AS ?objects)
WHERE {
  ?lesson a solo:Lesson ;
          rdfs:label ?lessonTitle ;
          solo:hasSection ?section .
  ?section rdfs:label ?sectionTitle ;
           solo:containsLearningObject ?lo .
}
GROUP BY ?lesson ?lessonTitle ?section ?sectionTitle
ORDER BY ?lessonTitle ?sectionTitle'''
            },
            'learning_objects': {
                'title': 'Learning Objects by Section',
                'query': '''PREFIX solo: <http://example.org/solo-education-ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?section ?sectionTitle ?lo ?title
WHERE {
  ?section a solo:Section ;
           rdfs:label ?sectionTitle ;
           solo:containsLearningObject ?lo .
  ?lo rdfs:label ?title .
}
ORDER BY ?sectionTitle ?title'''
            }
        }


# Create global instance
sparql_service = SPARQLService()
