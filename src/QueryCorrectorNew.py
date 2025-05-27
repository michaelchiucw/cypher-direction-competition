import re
from collections import namedtuple
from typing import Optional

Schema = namedtuple("Schema", ["left_node", "relation", "right_node"])

def load_schemas(str_schemas: str) -> list[Schema]:
    """Parses a string representation of schemas into a list of Schema objects.

    The input string is expected to contain schema definitions in the format
    "(nodeA_type, relation_type, nodeB_type), (nodeC_type, relation_type, nodeD_type)".
    Whitespace around names and delimiters is handled.

    Args:
        str_schemas: A string containing one or more schema definitions.
    
    Returns:
        A list of Schema named tuples, where each tuple represents a schema
        with `left_node`, `relation`, and `right_node` attributes.
    """
    # Regex to find all occurrences of (left_node, relation, right_node)
    # It captures 'left_node', 'relation', and 'right_node', allowing for optional whitespace
    # around names and delimiters.
    # Changed [^,]+? to [^,]*? to allow empty parts for nodes/relation.
    schema_pattern = re.compile(
        r"\(\s*(?P<left_node>[^,]*?)\s*,\s*(?P<relation>[^,]*?)\s*,\s*(?P<right_node>[^,]*?)\s*\)"
    )
    
    schemas = []
    for match in schema_pattern.finditer(str_schemas):
        schemas.append(
            Schema(
                match.group("left_node").strip(),
                match.group("relation").strip(),
                match.group("right_node").strip()
            )
        )
    return schemas


class QueryCorrector:
    
    property_pattern = re.compile(r"\{.+?\}")
    # node_pattern now captures the inner content of the node, excluding parentheses.
    node_pattern = re.compile(r"\(([^()]*?)\)")
    path_pattern = re.compile(r"(\([^\,\(\)]*?(\{.+\})?[^\,\(\)]*?\))(<?-)(\[.*?\])?(->?)(\([^\,\(\)]*?(\{.+\})?[^\,\(\)]*?\))")
    node_relation_node_pattern = re.compile(r"\((?P<left_node>[^()]*?)\)(?P<relation>.*?)\((?P<right_node>[^()]*?)\)")
    relation_type_pattern = re.compile(r":(?P<relation_type>.+?)?(\{.+\})?]")
    
    def __init__(self, schemas: list[Schema]):
        """Initializes the QueryCorrector with a list of valid schemas.

        The QueryCorrector uses these schemas to validate and correct Cypher query paths.
        The regex patterns for parsing Cypher queries are also compiled during initialization.

        Args:
            schemas: A list of Schema named tuples, representing the valid relationships
                     and node types in the graph.
        """
        self.schemas = schemas
    
    def clean_node_content(self, node_content: str) -> str:
        """Cleans the inner content of a Cypher node.
        Removes property blocks and strips leading/trailing whitespace.

        Args:
            node_content: The inner content of a node (e.g., "a:Label {prop:1}").
        
        Returns:
            The cleaned node content (e.g., "a:Label").
        """
        content = re.sub(self.property_pattern, "", node_content)
        content = content.strip()
        return content

    def detect_node_variables(self, query: str) -> dict[str, list[str]]:
        """Detects node variables and their labels from a Cypher query.

        Args:
            query: The Cypher query string.
        
        Returns:
            A dictionary where keys are node variables (or "" for anonymous nodes)
            and values are lists of label strings.
        """
        # self.node_pattern is r"\(([^()]*?)\)", so findall returns list of inner contents.
        node_contents = re.findall(self.node_pattern, query)
        res = {}
        for node_content in node_contents:
            cleaned_content = self.clean_node_content(node_content)
            
            if not cleaned_content:  # Skip if content is empty after cleaning
                continue
            
            parts = cleaned_content.split(":")
            # Example: "a:Label1:Label2" -> parts = ["a", "Label1", "Label2"]
            # Example: ":Label1" -> parts = ["", "Label1"]
            # Example: "a" -> parts = ["a"]
            
            variable = parts[0]  # Changed: No .strip()
            
            # Changed: No .strip() on labels, no filtering of empty/space-only labels.
            # If cleaned_content is "var::Label", parts is ["var", "", "Label"]. parts[1:] is ["", "Label"].
            # If cleaned_content is "var:", parts is ["var", ""]. parts[1:] is [""]
            actual_labels = parts[1:] 
            
            if variable not in res:
                res[variable] = []
            
            # If actual_labels is empty (e.g., from node "p" where parts=["p"]), parts[1:] is [].
            # res[variable].extend([]) works fine.
            # If actual_labels is [" Label "], res[variable].extend([" Label "]) is the desired behavior.
            res[variable].extend(actual_labels)
            
        return res

    def extract_paths(self, query: str) -> list[str]:
        """Extracts all distinct path patterns from a Cypher query.

        This method identifies path expressions like (n)-[r]->(m) and handles
        overlapping paths, such as (a)-->(b)-->(c), by extracting both
        (a)-->(b) and (b)-->(c).

        Args:
            query: The Cypher query string.
        
        Returns:
            A list of strings, where each string is a matched path pattern.
        """
        paths = []
        idx = 0
        # Loop as long as we are within the bounds of the query string
        while idx < len(query):
            # Attempt to find the next match starting from the current index 'idx'.
            # We use finditer and then break after the first match to re-evaluate 'idx'
            # for the next iteration, allowing for overlapping matches.
            match_found_in_current_finditer_call = False
            # finditer(query, pos=idx) ensures the search starts from 'idx'
            for match in self.path_pattern.finditer(query, pos=idx):
                # Construct the path string from captured groups:
                # Group 1: Left node (e.g., (a))
                # Group 3: Left arrow (e.g., <-, --)
                # Group 4: Relation details (e.g., [r:TYPE], optional)
                # Group 5: Right arrow (e.g., ->, --)
                # Group 6: Right node (e.g., (b))
                
                # These groups are guaranteed to exist if a match is found,
                # based on the structure of path_pattern.
                # Group 4 is optional in the regex (\[.*?\])?, so it can be None.
                g1 = match.group(1)
                g3 = match.group(3)
                g4 = match.group(4) or "" # Handle optional group 4
                g5 = match.group(5)
                g6 = match.group(6)

                path_str = g1 + g3 + g4 + g5 + g6
                paths.append(path_str)
                
                # Update idx to the start of the right node (group 6) of the current path.
                # This enables detection of overlapping paths. For example, in (a)-->(b)-->(c),
                # after matching "(a)-->(b)", the next search will start from index of "(b)".
                idx = match.start(6)
                match_found_in_current_finditer_call = True
                break  # Exit this for-loop to restart finditer with the new 'idx'
            
            # If the inner for-loop (finditer) did not find any match in this iteration,
            # it means no more paths can be found from the current 'idx' onwards.
            if not match_found_in_current_finditer_call:
                break # Exit the while-loop
        return paths

    def judge_direction(self, relation: str) -> str:
        """
        Args:
            relation: relation in string format
        """
        direction = "BIDIRECTIONAL"
        if relation[0] == "<":
            direction = "INCOMING"
        if relation[-1] == ">":
            direction = "OUTGOING"
        return direction

    def extract_node_variable(self, node_content: str) -> Optional[str]:
        """Extracts the variable name from a node's inner content.

        For example, for "n:Person", it returns "n". For ":Person", it returns None (or "" depending on impl).
        The current implementation returns None if the variable part is empty after stripping parentheses.

        Args:
            node_content: The inner content of a node string (e.g., "n:Person" or "(n:Person)").
        
        Returns:
            The node variable name as a string, or None if not found or empty.
        """
        # Ensure content is stripped of outer parentheses if any were passed
        if node_content.startswith("(") and node_content.endswith(")"):
            content = node_content[1:-1]
        else:
            content = node_content
            
        idx = content.find(":")
        if idx != -1:
            variable_part = content[:idx].strip()
        else:
            variable_part = content.strip()
            
        return variable_part if variable_part else None

    class _UncorrectablePathError(Exception):
        """Custom exception for when a path segment cannot be corrected."""
        pass

    def detect_labels(self, str_node_content: str, node_variable_dict: dict[str, list[str]]) -> list[str]:
        """Detects labels for a node, prioritizing globally known labels.

        Args:
            str_node_content: Inner content of a node (e.g., "n:Person {age:25}").
            node_variable_dict: Dictionary of node variables to their already known labels
                                (from the initial query scan). Keys are variable names,
                                values are lists of label strings.
        
        Returns:
            A list of label strings associated with the node.
        """
        cleaned_content = self.clean_node_content(str_node_content) # e.g., "n:Person"
        if not cleaned_content:
            return []
        
        parts = cleaned_content.split(":")
        # "a:Label1:Label2" -> parts = ["a", "Label1", "Label2"]
        # ":Label1" -> parts = ["", "Label1"]
        # "a" -> parts = ["a"]
        
        variable = parts[0].strip()
        
        # If variable is explicitly named and exists in the global dict, use its global labels.
        # This ensures consistency if a node's labels are fully defined elsewhere.
        # The check `if variable:` ensures this path is not taken for anonymous nodes (where variable == "").
        if variable and variable in node_variable_dict: 
            # If the variable is known globally and has labels, use them.
            # If it's known but has no labels (e.g. `(n)`), node_variable_dict[variable] would be [],
            # and we might fall through if we only checked `if variable in node_variable_dict`.
            # However, the prompt's target logic is `if variable and variable in node_variable_dict: return node_variable_dict[variable]`.
            # This implies if `variable` is known, its entry in `node_variable_dict` is the source of truth.
            # If `node_variable_dict[variable]` is `[]`, it means this named node has no labels globally.
            return node_variable_dict[variable]
        
        # Otherwise (anonymous node OR variable not in global dict OR variable in global dict but has no labels defined there),
        # parse labels from the local string content. This is crucial for anonymous nodes
        # and for nodes where labels are only specified in the current path segment.
        actual_labels = [lbl.strip() for lbl in parts[1:] if lbl.strip()]
        return actual_labels
    
    def verify_schema(self, from_node_labels: list[str], relation_types: list[str], to_node_labels: list[str]) -> bool:
        """Verifies if a given path segment (node-relation-node) conforms to any known schema.

        The verification considers the labels of the 'from' node, the type(s) of the relation,
        and the labels of the 'to' node.

        Args:
            from_node_labels: A list of labels for the starting node of the segment.
            relation_types: A list of types for the relation in the segment.
            to_node_labels: A list of labels for the ending node of the segment.
        
        Returns:
            True if the segment matches at least one schema, False otherwise.
        """
        valid_schemas = self.schemas
        if from_node_labels: # Check if list is not empty
            from_node_labels = [label.strip('`') for label in from_node_labels]
            valid_schemas = [schema for schema in valid_schemas if schema.left_node in from_node_labels]
        if to_node_labels: # Check if list is not empty
            to_node_labels = [label.strip('`') for label in to_node_labels]
            valid_schemas = [schema for schema in valid_schemas if schema.right_node in to_node_labels]
        if relation_types: # Check if list is not empty
            relation_types_stripped = [type_name.strip('`') for type_name in relation_types]
            valid_schemas = [schema for schema in valid_schemas if schema.relation in relation_types_stripped]
        
        return bool(valid_schemas)

    def _get_variable_from_node_content(self, node_inner_content: str) -> str:
        """Extracts the variable name from a node's inner content string."""
        cleaned_content = self.clean_node_content(node_inner_content)
        if not cleaned_content:
            return ""
        
        parts = cleaned_content.split(":", 1) # Split only on the first colon
        variable_name = parts[0].strip()
        return variable_name
    
    def detect_relation_types(self, str_relation: str) -> tuple[str, list[str]]:
        """
        Args:
            str_relation: relation in string format
        """
        relation_direction = self.judge_direction(str_relation)        
        relation_type = self.relation_type_pattern.search(str_relation)
        if relation_type is None or relation_type.group('relation_type') is None:
            return relation_direction, []
        relation_types = [t.strip().strip('!') for t in relation_type.group('relation_type').split("|")]
        return relation_direction, relation_types
        

    def correct_query(self, query: str) -> str:
        """
        Args:
            query: The Cypher query string to be corrected.
        
        Returns:
            The corrected Cypher query string if all paths are valid or correctable,
            or an empty string if any path is found to be uncorrectable.
        """
        # Store node variables for access by the helper method
        self._current_node_vars: dict[str, list[str]] = self.detect_node_variables(query)
        
        processed_query_parts = []
        # current_original_query_pos tracks how much of the original query string has been
        # accounted for and appended to processed_query_parts.
        current_original_query_pos = 0 
        
        # search_pos is where the next search for a path segment should begin in the original query.
        search_pos = 0 
        previous_match_right_node_full_text: Optional[str] = None

        try:
            while search_pos < len(query):
                match = self.path_pattern.search(query, pos=search_pos)
                if not match:
                    # No more path segments found, append the remainder of the query.
                    processed_query_parts.append(query[current_original_query_pos:])
                    break
                
                # Append the portion of the query string from the end of the last processed section
                # up to the beginning of the current matched segment.
                processed_query_parts.append(query[current_original_query_pos : match.start()])
                
                corrected_segment_str = self._process_path_match_for_correction(match)
                
                current_match_left_node_full_text = match.group(1)

                if (previous_match_right_node_full_text and 
                    corrected_segment_str.startswith(previous_match_right_node_full_text) and
                    current_match_left_node_full_text == previous_match_right_node_full_text):
                    # Overlap detected: current segment's left node is the same as the previous segment's right node.
                    # Append the corrected segment *without* its (duplicated) left node part.
                    # This assumes corrected_segment_str starts with the full text of its left node.
                    processed_query_parts.append(corrected_segment_str[len(previous_match_right_node_full_text):])
                else:
                    # No overlap with the previous segment's right node, or not a perfect textual match.
                    processed_query_parts.append(corrected_segment_str)
                
                # Update current_original_query_pos to the end of the current segment's original text
                current_original_query_pos = match.end()
                # Store the full text of the right node of the current match for the next iteration's overlap check.
                previous_match_right_node_full_text = match.group(6) 
                
                # Determine the start position for the next search.
                # To find chained paths like (A)-R1->(B)-R2->(C), the next search must start
                # at the beginning of (B) (the right node of the current segment).
                search_pos = match.start(6) # group(6) is the full text of the right node
                
                # Safety break: if search_pos isn't advancing properly, move to end of current match
                # to prevent potential infinite loops on unusual patterns.
                if search_pos <= match.start(): # match.start() is where the current segment search started
                    search_pos = match.end()
            
            return "".join(processed_query_parts)

        except QueryCorrector._UncorrectablePathError:
            return "" 
        finally:
            if hasattr(self, '_current_node_vars'):
                del self._current_node_vars
                
    def _process_path_match_for_correction(self, path_match_obj: re.Match) -> str:
        """Processes a single matched path, corrects its segments, or raises _UncorrectablePathError.

        This method is designed to be used as the replacement function in `re.sub`.
        It iterates over node-relation-node segments within the given path string,
        validates them against schemas, and applies corrections if necessary and possible.

        Args:
            path_match_obj: The match object from `re.sub` for `self.path_pattern`.
        
        Returns:
            The corrected path string.
        
        Raises:
            QueryCorrector._UncorrectablePathError: If any segment within the path
                                                   cannot be validated or corrected.
        """
        # This method processes a single path segment matched by self.path_pattern.
        # The internal while loop for iterating segments is removed.
        # Debugging prints are removed for the final fix.

        original_segment_str = path_match_obj.group(0)

        # Extract components from path_match_obj (match for self.path_pattern)
        # Group 1: Full text of the left node, e.g., (n1:Label1)
        # Group 3: Left arrow part of the relation, e.g., <-
        # Group 4: Relation specification, e.g., [r1:REL1] (optional)
        # Group 5: Right arrow part of the relation, e.g., ->
        # Group 6: Full text of the right node, e.g., (n2:Label2 {prop1:'val1'})
        
        left_node_full_text = path_match_obj.group(1)
        rel_part_left_arrow = path_match_obj.group(3)
        rel_part_spec = path_match_obj.group(4) or ""  # Handles optional relation spec
        rel_part_right_arrow = path_match_obj.group(5)
        right_node_full_text = path_match_obj.group(6)

        # Reconstruct the full relation string (e.g., <-[r1:REL1]- or -[r1:REL1]-> or -[r1:REL1]-)
        rel_str = rel_part_left_arrow + rel_part_spec + rel_part_right_arrow
        
        # Extract inner content from full node text for label detection
        # e.g., from "(n:Person {age:25})" to "n:Person {age:25}"
        ln_content_match = self.node_pattern.match(left_node_full_text)
        rn_content_match = self.node_pattern.match(right_node_full_text)

        if not ln_content_match or not rn_content_match:
            # This indicates a mismatch between path_pattern and node_pattern,
            # or an unexpected node structure. Should ideally not happen.
            # Returning original string is safer than raising an unexpected error.
            return original_segment_str 

        ln_content = ln_content_match.group(1)
        rn_content = rn_content_match.group(1)
            
        left_node_labels = self.detect_labels(ln_content, self._current_node_vars)
        right_node_labels = self.detect_labels(rn_content, self._current_node_vars)
        relation_direction, relation_types = self.detect_relation_types(rel_str)

        # Skip schema validation for variable-length paths; consider them structurally correct.
        if relation_types and any("*" in rt for rt in relation_types if isinstance(rt, str)):
            return original_segment_str

        corrected_rel_str = None 
        
        # Removed targeted debug prints for chained path from here

        if relation_direction == "OUTGOING": 
            if not self.verify_schema(left_node_labels, relation_types, right_node_labels): # Original direction invalid
                # Check if flip is possible by schema
                if self.verify_schema(right_node_labels, relation_types, left_node_labels): # Flipped direction IS valid by schema
                    # Now, check if nodes are anonymous before actually flipping
                    left_var = self._get_variable_from_node_content(ln_content)
                    right_var = self._get_variable_from_node_content(rn_content)
                    # The condition below prevented correction for anonymous nodes.
                    # Removing it allows correction based solely on schema validation.
                    # if left_var and right_var: # Both must be named to allow flip
                    corrected_rel_str = "<" + rel_str[:-1]
                    # Else: one or both nodes are anonymous, do not flip. corrected_rel_str remains None.
                else: # Flipped direction is also invalid by schema
                    raise QueryCorrector._UncorrectablePathError("Outgoing path segment uncorrectable.")
        elif relation_direction == "INCOMING":
            if not self.verify_schema(right_node_labels, relation_types, left_node_labels): # Original direction invalid
                # Check if flip is possible by schema
                if self.verify_schema(left_node_labels, relation_types, right_node_labels): # Flipped direction IS valid by schema
                    # Now, check if nodes are anonymous before actually flipping
                    left_var = self._get_variable_from_node_content(ln_content)
                    right_var = self._get_variable_from_node_content(rn_content)
                    # The condition below prevented correction for anonymous nodes.
                    # Removing it allows correction based solely on schema validation.
                    # if left_var and right_var: # Both must be named to allow flip
                    corrected_rel_str = rel_str[1:] + ">"
                    # Else: one or both nodes are anonymous, do not flip. corrected_rel_str remains None.
                else: # Flipped direction is also invalid by schema
                    raise QueryCorrector._UncorrectablePathError("Incoming path segment uncorrectable.")
        else:  # BIDIRECTIONAL
            is_L_R_valid = self.verify_schema(left_node_labels, relation_types, right_node_labels)
            is_R_L_valid = self.verify_schema(right_node_labels, relation_types, left_node_labels)
            if not (is_L_R_valid or is_R_L_valid):
                raise QueryCorrector._UncorrectablePathError("Bidirectional path segment uncorrectable.")

        if corrected_rel_str:
            # Reconstruct the full segment using original full node texts and the new relation string
            return f"{left_node_full_text}{corrected_rel_str}{right_node_full_text}"
        else:
            # No correction was needed or made
            return original_segment_str

    def __call__(self, query: str) -> str:
        """Corrects the given Cypher query to make its paths valid against known schemas.

        This is the main public method and entry point for the QueryCorrector.
        It internally calls the `correct_query` method. If a path cannot be
        corrected to match any schema, an empty string is returned.

        Args:
            query: The Cypher query string to correct.
        
        Returns:
            The corrected Cypher query string, or an empty string if correction fails.
        """
        return self.correct_query(query)