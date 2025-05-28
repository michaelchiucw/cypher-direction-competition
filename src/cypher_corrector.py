"""
This module provides functionality for correcting Cypher queries based on predefined schemas.
It includes classes and methods for parsing, validating, and correcting paths in Cypher queries
to ensure they conform to the expected schema definitions.

Note that this version is refined from the version at https://github.com/sakusaku-rich/cypher-direction-competition
for computational efficiency and improved readability.
"""

import re
from typing import Dict, List, Optional

from .cypher_schemas import Schema
from . import cypher_parser_utils


class CypherQueryCorrector:
    """A class for validating and correcting Cypher query paths against schemas.
    
    This class analyzes Cypher queries and corrects path directions to conform to the
    predefined schema definitions.
    """
    
    def __init__(self, schemas: List[Schema]):
        """Initializes the CypherQueryCorrector with a list of valid schemas.

        The CypherQueryCorrector uses these schemas to validate and correct Cypher query paths.

        Args:
            schemas: A list of Schema named tuples, representing the valid relationships
                     and node types in the graph.
        """
        self.schemas = schemas
    
    class _UncorrectablePathError(Exception):
        """Custom exception for when a path segment cannot be corrected."""
        pass
    
    def verify_schema(self, from_node_labels: List[str], relation_types: List[str], to_node_labels: List[str]) -> bool:
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
    
    def correct_query(self, query: str) -> str:
        """Corrects a Cypher query to make its paths valid against known schemas.

        Args:
            query: The Cypher query string to be corrected.
        
        Returns:
            The corrected Cypher query string if all paths are valid or correctable,
            or an empty string if any path is found to be uncorrectable.
        """
        # Store node variables for access by the helper method
        self._current_node_vars: Dict[str, List[str]] = cypher_parser_utils.detect_node_variables(query)
        
        processed_query_parts = []
        # current_original_query_pos tracks how much of the original query string has been
        # accounted for and appended to processed_query_parts.
        current_original_query_pos = 0 
        
        # search_pos is where the next search for a path segment should begin in the original query.
        search_pos = 0 
        previous_match_right_node_full_text: Optional[str] = None

        try:
            while search_pos < len(query):
                match = cypher_parser_utils.PATH_PATTERN.search(query, pos=search_pos)
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

        except CypherQueryCorrector._UncorrectablePathError:
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
            CypherQueryCorrector._UncorrectablePathError: If any segment within the path
                                                   cannot be validated or corrected.
        """
        # This method processes a single path segment matched by PATH_PATTERN.
        original_segment_str = path_match_obj.group(0)

        # Extract components from path_match_obj
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
        ln_content_match = cypher_parser_utils.NODE_PATTERN.match(left_node_full_text)
        rn_content_match = cypher_parser_utils.NODE_PATTERN.match(right_node_full_text)

        if not ln_content_match or not rn_content_match:
            # This indicates a mismatch between path_pattern and node_pattern,
            # or an unexpected node structure. Should ideally not happen.
            # Returning original string is safer than raising an unexpected error.
            return original_segment_str 

        ln_content = ln_content_match.group(1)
        rn_content = rn_content_match.group(1)
            
        left_node_labels = cypher_parser_utils.detect_labels(ln_content, self._current_node_vars)
        right_node_labels = cypher_parser_utils.detect_labels(rn_content, self._current_node_vars)
        relation_direction, relation_types = cypher_parser_utils.detect_relation_types(rel_str)

        # Skip schema validation for variable-length paths; consider them structurally correct.
        if relation_types and any("*" in rt for rt in relation_types if isinstance(rt, str)):
            return original_segment_str

        corrected_rel_str = None 
        
        if relation_direction == "OUTGOING": 
            if not self.verify_schema(left_node_labels, relation_types, right_node_labels): # Original direction invalid
                # Check if flip is possible by schema
                if self.verify_schema(right_node_labels, relation_types, left_node_labels): # Flipped direction IS valid by schema
                    # Now, check if nodes are anonymous before actually flipping
                    left_var = cypher_parser_utils._get_variable_from_node_content(ln_content)
                    right_var = cypher_parser_utils._get_variable_from_node_content(rn_content)
                    corrected_rel_str = "<" + rel_str[:-1]
                else: # Flipped direction is also invalid by schema
                    raise CypherQueryCorrector._UncorrectablePathError("Outgoing path segment uncorrectable.")
        elif relation_direction == "INCOMING":
            if not self.verify_schema(right_node_labels, relation_types, left_node_labels): # Original direction invalid
                # Check if flip is possible by schema
                if self.verify_schema(left_node_labels, relation_types, right_node_labels): # Flipped direction IS valid by schema
                    # Now, check if nodes are anonymous before actually flipping
                    left_var = cypher_parser_utils._get_variable_from_node_content(ln_content)
                    right_var = cypher_parser_utils._get_variable_from_node_content(rn_content)
                    corrected_rel_str = rel_str[1:] + ">"
                else: # Flipped direction is also invalid by schema
                    raise CypherQueryCorrector._UncorrectablePathError("Incoming path segment uncorrectable.")
        else:  # BIDIRECTIONAL
            is_L_R_valid = self.verify_schema(left_node_labels, relation_types, right_node_labels)
            is_R_L_valid = self.verify_schema(right_node_labels, relation_types, left_node_labels)
            if not (is_L_R_valid or is_R_L_valid):
                raise CypherQueryCorrector._UncorrectablePathError("Bidirectional path segment uncorrectable.")

        if corrected_rel_str:
            # Reconstruct the full segment using original full node texts and the new relation string
            return f"{left_node_full_text}{corrected_rel_str}{right_node_full_text}"
        else:
            # No correction was needed or made
            return original_segment_str

    def __call__(self, query: str) -> str:
        """Corrects the given Cypher query to make its paths valid against known schemas.

        This is the main public method and entry point for the CypherQueryCorrector.
        It internally calls the `correct_query` method. If a path cannot be
        corrected to match any schema, an empty string is returned.

        Args:
            query: The Cypher query string to correct.
        
        Returns:
            The corrected Cypher query string, or an empty string if correction fails.
        """
        return self.correct_query(query)
