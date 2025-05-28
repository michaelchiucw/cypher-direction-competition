import unittest
import sys
import os
import importlib # Added

# Adjust the path to import from the parent directory (src)
# This allows finding 'src.QueryCorrector' and 'src.QueryCorrectorNew'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Removed direct imports:
# from QueryCorrector import QueryCorrector, Schema, load_schemas

class _QueryCorrectorTestCase(unittest.TestCase):
    # MODULE_UNDER_TEST_NAME will be set by subclasses
    MODULE_UNDER_TEST_NAME: str = ""
    # CLASS_NAME will be set by subclasses if the class is not named QueryCorrector
    CLASS_NAME: str = "QueryCorrector"

    def setUp(self):
        """Set up a QueryCorrector instance with a fixed set of schemas for tests."""
        if not self.MODULE_UNDER_TEST_NAME:
            self.skipTest("MODULE_UNDER_TEST_NAME not set in subclass")

        self.module_to_test = importlib.import_module(self.MODULE_UNDER_TEST_NAME)
        
        # Get the corrector class, which might have a different name in different modules
        QueryCorrectorCls = getattr(self.module_to_test, self.CLASS_NAME)
        self.Schema = self.module_to_test.Schema # Store SchemaCls as self.Schema

        self.schemas = [
            self.Schema("Person", "WORKS_AT", "Company"),
            self.Schema("Person", "FRIENDS_WITH", "Person"),
            self.Schema("Company", "HAS_PRODUCT", "Product"),
            self.Schema("Person", "LIKES", "Product"),
            self.Schema("Animal", "HAS_PET", "Person"), 
        ]
        self.corrector = QueryCorrectorCls(self.schemas)
        self.empty_schema_corrector = QueryCorrectorCls([])

    def test_load_schemas(self):
        # Use self.module_to_test.load_schemas and self.Schema
        self.assertEqual(self.module_to_test.load_schemas(""), [])
        self.assertEqual(self.module_to_test.load_schemas("()"), [])
        self.assertEqual(self.module_to_test.load_schemas("(,,)"), [])

        schemas_str = "(Person, KNOWS, Person)"
        expected = [self.Schema("Person", "KNOWS", "Person")]
        self.assertEqual(self.module_to_test.load_schemas(schemas_str), expected)

        schemas_str_ws = "(  Person  ,  KNOWS  ,  Person  )"
        self.assertEqual(self.module_to_test.load_schemas(schemas_str_ws), expected, "Whitespace handling")

        schemas_str_multi = "(Person, KNOWS, Person),(User, FOLLOWS, User)"
        expected_multi = [
            self.Schema("Person", "KNOWS", "Person"),
            self.Schema("User", "FOLLOWS", "User")
        ]
        self.assertEqual(self.module_to_test.load_schemas(schemas_str_multi), expected_multi)
        
        schemas_str_multi_ws = "( Person,KNOWS,Person ) , ( User, FOLLOWS  , User)"
        self.assertEqual(self.module_to_test.load_schemas(schemas_str_multi_ws), expected_multi, "Multi with varied whitespace")

        self.assertEqual(self.module_to_test.load_schemas("(Person,KNOWS)"), [], "Malformed entry (too few parts)")
        self.assertEqual(self.module_to_test.load_schemas("(Person,KNOWS,Person,Extra)"), [], "Malformed entry (too many parts)")
        self.assertEqual(self.module_to_test.load_schemas("Person,KNOWS,Person"), [], "Missing parentheses")
        
        s = "(  nodeA  , relation1,nodeB ),(nodeC,relation2, nodeD)"
        e = [self.Schema('nodeA','relation1','nodeB'), self.Schema('nodeC','relation2','nodeD')]
        self.assertEqual(self.module_to_test.load_schemas(s), e)

        s = "(label1, type1,label2)"
        e = [self.Schema('label1','type1','label2')]
        self.assertEqual(self.module_to_test.load_schemas(s), e)

    def test_clean_node_content(self):
        test_cases = [
            # description, input_for_old_clean_node, input_for_new_clean_node_content, expected_output
            ("Basic cleaning with props", "(n:Person {name:'Alice'})", "n:Person {name:'Alice'}", "n:Person"),
            ("No props", "(n:Person)", "n:Person", "n:Person"),
            ("Whitespace and props", "(  n:Person {name:'Alice'}  )", "  n:Person {name:'Alice'}  ", "n:Person"),
            ("Whitespace no props", "(  n:Person  )", "  n:Person  ", "n:Person"),
            ("Only properties", "({name:'Alice'})", "{name:'Alice'}", ""),
            ("Only variable", "(n)", "n", "n"),
            ("Only label", "(:Person)", ":Person", ":Person"),
            ("Multiple labels and props", "(n:Person:User {id:1})", "n:Person:User {id:1}", "n:Person:User"),
            ("Empty content in parens for old", "()", "", ""), # Old clean_node gets "()", new gets ""
            ("Whitespace only in parens for old", "(   )", "   ", ""), # Old clean_node gets "(   )", new gets "   "
            ("Only properties and whitespace", "(  {name:'Alice'}  )", "  {name:'Alice'}  ", "")
        ]

        for desc, old_input, new_input, expected in test_cases:
            with self.subTest(msg=desc):
                if self.MODULE_UNDER_TEST_NAME == "src.QueryCorrector":
                    # Old version expects full node string like "(content)"
                    # and has a method named 'clean_node'
                    self.assertEqual(self.corrector.clean_node(old_input), expected)
                else: # For "src.QueryCorrectorNew"
                    # New version expects inner content string
                    # and has a method named 'clean_node_content'
                    self.assertEqual(self.corrector.clean_node_content(new_input), expected)
        
        # Specific test for old version with empty string (not in parens)
        if self.MODULE_UNDER_TEST_NAME == "src.QueryCorrector":
             with self.subTest(msg="Old version empty string input"):
                self.assertEqual(self.corrector.clean_node(""), "") # Old clean_node with "" input
                self.assertEqual(self.corrector.clean_node("   "), "") # Old clean_node with "   " input


    def test_detect_node_variables(self):
        query1 = "MATCH (p:Person)"
        expected1 = {"p": ["Person"]}
        self.assertDictEqual(self.corrector.detect_node_variables(query1), expected1)

        query2 = "MATCH (p:Person {name: 'Alice'})"
        self.assertDictEqual(self.corrector.detect_node_variables(query2), expected1)

        query3 = "MATCH (p:Person:User)"
        expected3 = {"p": ["Person", "User"]}
        self.assertDictEqual(self.corrector.detect_node_variables(query3), expected3)
        
        query4 = "MATCH (p:Person), (c:Company)"
        expected4 = {"p": ["Person"], "c": ["Company"]}
        self.assertDictEqual(self.corrector.detect_node_variables(query4), expected4)

        query5 = "MATCH (:Person)"
        expected5 = {"": ["Person"]}
        self.assertDictEqual(self.corrector.detect_node_variables(query5), expected5)

        query6 = "MATCH (p:Person), (:User)"
        expected6 = {"p": ["Person"], "": ["User"]}
        self.assertDictEqual(self.corrector.detect_node_variables(query6), expected6)
        
        query7 = "MATCH (p)"
        expected7 = {"p": []}
        self.assertDictEqual(self.corrector.detect_node_variables(query7), expected7)

        query8 = "RETURN 1"
        expected8 = {}
        self.assertDictEqual(self.corrector.detect_node_variables(query8), expected8)

        query9 = ""
        expected9 = {}
        self.assertDictEqual(self.corrector.detect_node_variables(query9), expected9)

        query10 = "MATCH (a:Actor {name:'Tom Hanks'}), (m:Movie:Film), (d), (:Director), (a)-[:ACTED_IN]->(m)"
        expected10 = {
            "a": ["Actor"],
            "m": ["Movie", "Film"],
            "d": [],
            "": ["Director"]
        }
        detected_vars = self.corrector.detect_node_variables(query10)
        for var, labels in expected10.items():
            self.assertIn(var, detected_vars)
            self.assertListEqual(sorted(detected_vars[var]), sorted(labels))

        query11 = "MATCH (  p  :  Person   : User {name: 'X'} )"
        expected11 = {"p": ["Person", "User"]}
        detected_vars11 = self.corrector.detect_node_variables(query11)
        self.assertIn("p", detected_vars11)
        self.assertListEqual(sorted(detected_vars11["p"]), sorted(expected11["p"]))

    def test_extract_paths(self):
        query1 = "MATCH (a)-[r]->(b) RETURN a, b"
        expected1 = ["(a)-[r]->(b)"]
        self.assertListEqual(self.corrector.extract_paths(query1), expected1)

        query2 = "MATCH (a:Person {name:'A'})-[r:KNOWS {since:2020}]->(b:Person {name:'B'})"
        expected2 = ["(a:Person {name:'A'})-[r:KNOWS {since:2020}]->(b:Person {name:'B'})"]
        self.assertListEqual(self.corrector.extract_paths(query2), expected2)

        query3 = "MATCH (a)-->(b), (c)<--(d)"
        expected3 = ["(a)-->(b)", "(c)<--(d)"]
        self.assertListEqual(self.corrector.extract_paths(query3), expected3)

        query4 = "MATCH (a)-[r1]->(b)<-[r2]-(c)"
        expected4 = ["(a)-[r1]->(b)", "(b)<-[r2]-(c)"]
        self.assertListEqual(self.corrector.extract_paths(query4), expected4)

        query5 = "MATCH (a)-[r1]->(b)-[r2]->(c)"
        expected5 = ["(a)-[r1]->(b)", "(b)-[r2]->(c)"]
        self.assertListEqual(self.corrector.extract_paths(query5), expected5)

        query6 = "MATCH (a)-[]->(b)"
        expected6 = ["(a)-[]->(b)"]
        self.assertListEqual(self.corrector.extract_paths(query6), expected6)
        
        query7 = "MATCH (a)-[r]-(b)"
        expected7 = ["(a)-[r]-(b)"]
        self.assertListEqual(self.corrector.extract_paths(query7), expected7)

        query8 = "MATCH (a)<-[r]-(b)"
        expected8 = ["(a)<-[r]-(b)"]
        self.assertListEqual(self.corrector.extract_paths(query8), expected8)

        query9 = "MATCH (a), (b) RETURN a, b"
        expected9 = []
        self.assertListEqual(self.corrector.extract_paths(query9), expected9)

        query10 = ""
        expected10 = []
        self.assertListEqual(self.corrector.extract_paths(query10), expected10)
        
        query11 = "MATCH (n1:Label1)-[r1:REL1]->(n2:Label2 {prop1:'val1'})<-[r2:REL2 {prop2:'val2'}]-(n3:Label3) RETURN n1,n2,n3"
        expected11 = [
            "(n1:Label1)-[r1:REL1]->(n2:Label2 {prop1:'val1'})",
            "(n2:Label2 {prop1:'val1'})<-[r2:REL2 {prop2:'val2'}]-(n3:Label3)"
        ]
        self.assertListEqual(self.corrector.extract_paths(query11), expected11)

        query12 = "MATCH (a)-[r]->" 
        expected12 = []
        self.assertListEqual(self.corrector.extract_paths(query12), expected12)

        query13 = "MATCH (a)-[r]-(b)-[r2]-(c)-[r3]-(d)"
        expected13 = ["(a)-[r]-(b)", "(b)-[r2]-(c)", "(c)-[r3]-(d)"]
        self.assertListEqual(self.corrector.extract_paths(query13), expected13)

    def test_detect_relation_types(self):
        self.assertEqual(self.corrector.detect_relation_types("-->"), ("OUTGOING", []))
        self.assertEqual(self.corrector.detect_relation_types("<--"), ("INCOMING", []))
        self.assertEqual(self.corrector.detect_relation_types("--"), ("BIDIRECTIONAL", []))
        self.assertEqual(self.corrector.detect_relation_types("-[r:KNOWS]->"), ("OUTGOING", ["KNOWS"]))
        self.assertEqual(self.corrector.detect_relation_types("<-[r:WORKS_AT]-"), ("INCOMING", ["WORKS_AT"]))
        self.assertEqual(self.corrector.detect_relation_types("-[r:FRIENDS_WITH]-"), ("BIDIRECTIONAL", ["FRIENDS_WITH"]))
        self.assertEqual(self.corrector.detect_relation_types("-[r:TYPE1|TYPE2]->"), ("OUTGOING", ["TYPE1", "TYPE2"]))
        self.assertEqual(self.corrector.detect_relation_types("-[r:!TYPE1|TYPE2]->"), ("OUTGOING", ["TYPE1", "TYPE2"]))
        self.assertEqual(self.corrector.detect_relation_types("-[r:KNOWS*1..5]->"), ("OUTGOING", ["KNOWS*1..5"]))
        self.assertEqual(self.corrector.detect_relation_types("-[r:*]->"), ("OUTGOING", ["*"]))
        self.assertEqual(self.corrector.detect_relation_types("-[r:LIKES {how_much:'lots'}]->"), ("OUTGOING", ["LIKES"]))
        self.assertEqual(self.corrector.detect_relation_types("-[:]->"), ("OUTGOING", []))
        self.assertEqual(self.corrector.detect_relation_types("-[r:]->"), ("OUTGOING", []))
        self.assertEqual(self.corrector.detect_relation_types("-[NO_TYPE_HERE]->"), ("OUTGOING", []))
        self.assertEqual(self.corrector.detect_relation_types("-[r]->"), ("OUTGOING", []))
        self.assertEqual(self.corrector.detect_relation_types("-[r:  KNOWS  ]->"), ("OUTGOING", ["KNOWS"]))
        self.assertEqual(self.corrector.detect_relation_types("-[r:TYPE1 | TYPE2]->"), ("OUTGOING", ["TYPE1", "TYPE2"]))

    def test_verify_schema(self):
        self.assertTrue(self.corrector.verify_schema(["Person"], ["WORKS_AT"], ["Company"]))
        self.assertTrue(self.corrector.verify_schema(["Person"], ["FRIENDS_WITH"], ["Person"]))
        self.assertTrue(self.corrector.verify_schema(["Company"], ["HAS_PRODUCT"], ["Product"]))
        self.assertTrue(self.corrector.verify_schema(["Person"], ["LIKES"], ["Product"]))
        self.assertTrue(self.corrector.verify_schema(["Animal"], ["HAS_PET"], ["Person"]))
        self.assertFalse(self.corrector.verify_schema(["Company"], ["WORKS_AT"], ["Person"]))
        self.assertFalse(self.corrector.verify_schema(["Person"], ["OWNS"], ["Company"]))
        self.assertFalse(self.corrector.verify_schema(["Person"], ["WORKS_AT"], ["Product"]))
        self.assertTrue(self.corrector.verify_schema([], ["WORKS_AT"], ["Company"]), "Any source, WORKS_AT, Company")
        self.assertTrue(self.corrector.verify_schema(["Person"], [], ["Company"]), "Person, Any relation, Company")
        self.assertTrue(self.corrector.verify_schema(["Person"], ["WORKS_AT"], []), "Person, WORKS_AT, Any target")
        self.assertTrue(self.corrector.verify_schema([], [], []), "Any source, Any relation, Any target (matches any schema)")
        self.assertFalse(self.empty_schema_corrector.verify_schema(["Person"], ["WORKS_AT"], ["Company"]))
        self.assertFalse(self.empty_schema_corrector.verify_schema([], [], []))
        self.assertTrue(self.corrector.verify_schema(["Person", "Manager"], ["FRIENDS_WITH"], ["Person"]))
        self.assertTrue(self.corrector.verify_schema(["Person"], ["FRIENDS_WITH"], ["Person", "Colleague"]))
        self.assertTrue(self.corrector.verify_schema(["Person"], ["WORKS_AT", "FORMERLY_WORKS_AT"], ["Company"]))
        self.assertTrue(self.corrector.verify_schema(["Person"], ["WORKS_AT", "IS_EMPLOYED_BY"], ["Company"]))
        self.assertFalse(self.corrector.verify_schema(["Person"], ["IS_CEO_OF", "IS_BOARD_MEMBER_OF"], ["Company"]))
        self.assertTrue(self.corrector.verify_schema(["`Person`"], ["`WORKS_AT`"], ["`Company`"]))

    # --- Tests for correct_query ---
    def test_correct_query_already_correct(self):
        query1 = "MATCH (p:Person)-[:WORKS_AT]->(c:Company) RETURN p, c"
        self.assertEqual(self.corrector.correct_query(query1), query1)
        query2 = "MATCH (p1:Person)-[:FRIENDS_WITH]->(p2:Person) RETURN p1, p2"
        self.assertEqual(self.corrector.correct_query(query2), query2)
        query3 = "MATCH (p1:Person)-[:FRIENDS_WITH]-(p2:Person) RETURN p1, p2"
        self.assertEqual(self.corrector.correct_query(query3), query3)
        query4 = "MATCH (a:Animal)-[:HAS_PET]->(p:Person) RETURN a,p"
        self.assertEqual(self.corrector.correct_query(query4), query4)

    def test_correct_query_needs_direction_flip(self):
        query_original = "MATCH (c:Company)-[:WORKS_AT]->(p:Person) RETURN c,p"
        query_expected = "MATCH (c:Company)<-[:WORKS_AT]-(p:Person) RETURN c,p"
        self.assertEqual(self.corrector.correct_query(query_original), query_expected)
        query_original_2 = "MATCH (p:Person)-[:HAS_PET]->(a:Animal) RETURN p,a"
        query_expected_2 = "MATCH (p:Person)<-[:HAS_PET]-(a:Animal) RETURN p,a"
        self.assertEqual(self.corrector.correct_query(query_original_2), query_expected_2)
        query_original_3 = "MATCH (p1:Person)<-[:FRIENDS_WITH]-(p2:Person) RETURN p1,p2"
        self.assertEqual(self.corrector.correct_query(query_original_3), query_original_3)
        query_original_4 = "MATCH (c:Company), (p:Person) WHERE c.name = 'Comp' AND p.name = 'Pers' MATCH (c)-[:WORKS_AT]->(p) RETURN c,p"
        query_expected_4 = "MATCH (c:Company), (p:Person) WHERE c.name = 'Comp' AND p.name = 'Pers' MATCH (c)<-[:WORKS_AT]-(p) RETURN c,p"
        self.assertEqual(self.corrector.correct_query(query_original_4), query_expected_4)

    def test_correct_query_uncorrectable(self):
        query1 = "MATCH (p:Person)-[:EMPLOYED_BY]->(c:Company) RETURN p, c"
        self.assertEqual(self.corrector.correct_query(query1), "")
        query2 = "MATCH (p:Person)-[:WORKS_AT]->(pr:Product) RETURN p, pr"
        self.assertEqual(self.corrector.correct_query(query2), "")
        query3 = "MATCH (p:Product)-[:WORKS_AT]->(c:Company) RETURN p, c"
        self.assertEqual(self.corrector.correct_query(query3), "")
        query4 = "MATCH (p:Person)-[:WORKS_AT]->(c:Company) RETURN p, c"
        self.assertEqual(self.empty_schema_corrector.correct_query(query4), "")

    def test_correct_query_multiple_paths(self):
        query1 = "MATCH (p:Person)-[:WORKS_AT]->(c:Company), (p)-[:LIKES]->(pr:Product) RETURN p"
        self.assertEqual(self.corrector.correct_query(query1), query1)
        query2_orig = "MATCH (c:Company)-[:WORKS_AT]->(p:Person), (p)-[:LIKES]->(pr:Product) RETURN p"
        query2_expected = "MATCH (c:Company)<-[:WORKS_AT]-(p:Person), (p)-[:LIKES]->(pr:Product) RETURN p"
        self.assertEqual(self.corrector.correct_query(query2_orig), query2_expected)
        query3 = "MATCH (p:Person)-[:WORKS_AT]->(c:Company), (p)-[:OWNS]->(pr:Product) RETURN p"
        self.assertEqual(self.corrector.correct_query(query3), "")

    def test_correct_query_chained_paths_correction(self):
        query1 = "MATCH (c:Company)<-[:WORKS_AT]-(p:Person)-[:LIKES]->(pr:Product) RETURN c,p,pr"
        self.assertEqual(self.corrector.correct_query(query1), query1)
        query2_orig = "MATCH (p:Person)-[:WORKS_AT]->(c:Company)<-[:HAS_PRODUCT]-(pr:Product) RETURN p,c,pr"
        query2_expected = "MATCH (p:Person)-[:WORKS_AT]->(c:Company)-[:HAS_PRODUCT]->(pr:Product) RETURN p,c,pr"
        self.assertEqual(self.corrector.correct_query(query2_orig), query2_expected)
        query3_orig = "MATCH (p:Person)<-[:LIKES]-(pr:Product)-[:HAS_PRODUCT]->(c:Company) RETURN p,c,pr"
        query3_expected = "MATCH (p:Person)-[:LIKES]->(pr:Product)<-[:HAS_PRODUCT]-(c:Company) RETURN p,c,pr"
        self.assertEqual(self.corrector.correct_query(query3_orig), query3_expected)
        query4_orig = "MATCH (p:Person)-[:WORKS_AT]->(c:Company)-[:FRIENDS_WITH]->(p2:Person) RETURN p,c,p2"
        self.assertEqual(self.corrector.correct_query(query4_orig), "")

    def test_correct_query_anonymous_nodes(self):
        query1_orig = "MATCH (:Company)-[:WORKS_AT]->(:Person)"
        query1_expected = "MATCH (:Company)<-[:WORKS_AT]-(:Person)"
        self.assertEqual(self.corrector.correct_query(query1_orig), query1_expected)
        query2 = "MATCH (:Person)-[:LIKES]->(:Product)"
        self.assertEqual(self.corrector.correct_query(query2), query2)
        query3 = "MATCH (:Person)-[:WORKS_AT]->(:Person)"
        self.assertEqual(self.corrector.correct_query(query3), "")

    def test_correct_query_variable_length_relations(self):
        query1 = "MATCH (p:Person)-[:FRIENDS_WITH*]->(p2:Person)"
        self.assertEqual(self.corrector.correct_query(query1), query1)
        query2 = "MATCH (p:Person)-[:WORKS_AT*]->(c:Company)"
        self.assertEqual(self.corrector.correct_query(query2), query2)
        query3 = "MATCH (p:Person)-[:OWNS_HOUSE*]->(h:House)" 
        self.assertEqual(self.corrector.correct_query(query3), query3)
        query4_orig = "MATCH (p:Person)-[:WORKS_AT*1..2]->(c:Company)-[:LIKES]->(p2:Person)"
        self.assertEqual(self.corrector.correct_query(query4_orig), "")

    def test_correct_query_no_paths(self):
        query = "MATCH (p:Person) RETURN p"
        self.assertEqual(self.corrector.correct_query(query), query)

    def test_correct_query_empty_query(self):
        query = ""
        self.assertEqual(self.corrector.correct_query(query), query)
        
    def test_query_from_problem_description(self):
        # This test now uses self.module_to_test and self.Schema
        schemas_str = "(label1, type1, label2), (label2, type2, label3)"
        # Use self.module_to_test.load_schemas and self.Schema
        schemas = self.module_to_test.load_schemas(schemas_str)
        
        # Get QueryCorrector class from the dynamically loaded module
        QueryCorrectorCls = getattr(self.module_to_test, self.CLASS_NAME)
        corrector = QueryCorrectorCls(schemas)

        query = "MATCH (n1:label1)-[r1:type1]->(n2:label2)-[r2:type2]->(n3:label3) RETURN n1, n2, n3"
        self.assertEqual(corrector.correct_query(query), query)

        query_needs_flip = "MATCH (n1:label1)<-[r1:type1]-(n2:label2)-[r2:type2]->(n3:label3) RETURN n1, n2, n3"
        expected_flip = "MATCH (n1:label1)-[r1:type1]->(n2:label2)-[r2:type2]->(n3:label3) RETURN n1, n2, n3"
        self.assertEqual(corrector.correct_query(query_needs_flip), expected_flip)

        query_uncorrectable = "MATCH (n1:label1)-[r1:type2]->(n2:label2) RETURN n1,n2"
        self.assertEqual(corrector.correct_query(query_uncorrectable), "")

# Concrete test classes
class TestOriginalImplementation(_QueryCorrectorTestCase):
    MODULE_UNDER_TEST_NAME = "src.QueryCorrector"

class TestNewImplementation(_QueryCorrectorTestCase):
    MODULE_UNDER_TEST_NAME = "src.QueryCorrectorNew"
    
class TestCypherImplementation(_QueryCorrectorTestCase):
    MODULE_UNDER_TEST_NAME = "src.cypher_corrector"
    CLASS_NAME = "CypherQueryCorrector"

if __name__ == '__main__':
    unittest.main()
