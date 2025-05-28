"""
This module provides utility functions for parsing and dissecting Cypher query strings.
It contains various regex patterns and functions to extract and analyze components of Cypher queries.

Note that this file is part of the refinement of the version at https://github.com/sakusaku-rich/cypher-direction-competition
for computational efficiency and improved readability.
"""

import re
from typing import Dict, List, Optional, Tuple

# Regex patterns for parsing Cypher queries
PROPERTY_PATTERN = re.compile(r"\{.+?\}")
NODE_PATTERN = re.compile(r"\(([^()]*?)\)")
PATH_PATTERN = re.compile(r"(\([^\,\(\)]*?(\{.+\})?[^\,\(\)]*?\))(<?-)(\[.*?\])?(->?)(\([^\,\(\)]*?(\{.+\})?[^\,\(\)]*?\))")
NODE_RELATION_NODE_PATTERN = re.compile(r"\((?P<left_node>[^()]*?)\)(?P<relation>.*?)\((?P<right_node>[^()]*?)\)")
RELATION_TYPE_PATTERN = re.compile(r":(?P<relation_type>.+?)?(\{.+\})?]")

def clean_node_content(node_content: str) -> str:
    """Cleans the inner content of a Cypher node.
    Removes property blocks and strips leading/trailing whitespace.

    Args:
        node_content: The inner content of a node (e.g., "a:Label {prop:1}").
    
    Returns:
        The cleaned node content (e.g., "a:Label").
    """
    content = re.sub(PROPERTY_PATTERN, "", node_content)
    content = content.strip()
    return content

def detect_node_variables(query: str) -> Dict[str, List[str]]:
    """Detects node variables and their labels from a Cypher query.

    Args:
        query: The Cypher query string.
    
    Returns:
        A dictionary where keys are node variables (or "" for anonymous nodes)
        and values are lists of label strings.
    """
    # NODE_PATTERN is r"\(([^()]*?)\)", so findall returns list of inner contents.
    node_contents = re.findall(NODE_PATTERN, query)
    res = {}
    for node_content in node_contents:
        cleaned_content = clean_node_content(node_content)
        
        if not cleaned_content:  # Skip if content is empty after cleaning
            continue
        
        parts = cleaned_content.split(":")
        # Example: "a:Label1:Label2" -> parts = ["a", "Label1", "Label2"]
        # Example: ":Label1" -> parts = ["", "Label1"]
        # Example: "a" -> parts = ["a"]
        
        variable = parts[0]  # No .strip() needed as cleaned_content is already stripped
        
        # No .strip() on labels, no filtering of empty/space-only labels.
        actual_labels = parts[1:] 
        
        if variable not in res:
            res[variable] = []
        
        res[variable].extend(actual_labels)
        
    return res

def extract_paths(query: str) -> List[str]:
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
        for match in PATH_PATTERN.finditer(query, pos=idx):
            # Construct the path string from captured groups:
            # Group 1: Left node (e.g., (a))
            # Group 3: Left arrow (e.g., <-, --)
            # Group 4: Relation details (e.g., [r:TYPE], optional)
            # Group 5: Right arrow (e.g., ->, --)
            # Group 6: Right node (e.g., (b))
            
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

def judge_direction(relation: str) -> str:
    """Determines the direction of a relation in a Cypher path.

    Args:
        relation: The relation string from a path (e.g., "<-", "->", "-")
    
    Returns:
        A string indicating the direction: "INCOMING", "OUTGOING", or "BIDIRECTIONAL".
    """
    direction = "BIDIRECTIONAL"
    if relation[0] == "<":
        direction = "INCOMING"
    if relation[-1] == ">":
        direction = "OUTGOING"
    return direction

def extract_node_variable(node_content: str) -> Optional[str]:
    """Extracts the variable name from a node's inner content.

    For example, for "n:Person", it returns "n". For ":Person", it returns None.
    The implementation returns None if the variable part is empty after stripping parentheses.

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

def _get_variable_from_node_content(node_inner_content: str) -> str:
    """Extracts the variable name from a node's inner content string.
    
    Args:
        node_inner_content: Inner content of a node (e.g., "n:Person {age:25}").
        
    Returns:
        The variable name as a string, or an empty string if no variable is found.
    """
    cleaned_content = clean_node_content(node_inner_content)
    if not cleaned_content:
        return ""
    
    parts = cleaned_content.split(":", 1) # Split only on the first colon
    variable_name = parts[0].strip()
    return variable_name

def detect_labels(str_node_content: str, node_variable_dict: Dict[str, List[str]]) -> List[str]:
    """Detects labels for a node, prioritizing globally known labels.

    Args:
        str_node_content: Inner content of a node (e.g., "n:Person {age:25}").
        node_variable_dict: Dictionary of node variables to their already known labels
                            (from the initial query scan). Keys are variable names,
                            values are lists of label strings.
    
    Returns:
        A list of label strings associated with the node.
    """
    cleaned_content = clean_node_content(str_node_content) # e.g., "n:Person"
    if not cleaned_content:
        return []
    
    parts = cleaned_content.split(":")
    # "a:Label1:Label2" -> parts = ["a", "Label1", "Label2"]
    # ":Label1" -> parts = ["", "Label1"]
    # "a" -> parts = ["a"]
    
    variable = parts[0].strip()
    
    # If variable is explicitly named and exists in the global dict, use its global labels.
    # This ensures consistency if a node's labels are fully defined elsewhere.
    if variable and variable in node_variable_dict: 
        return node_variable_dict[variable]
    
    # Otherwise parse labels from the local string content.
    actual_labels = [lbl.strip() for lbl in parts[1:] if lbl.strip()]
    return actual_labels

def detect_relation_types(str_relation: str) -> Tuple[str, List[str]]:
    """Detects relation types and direction from a relation string.

    Args:
        str_relation: The relation string from a path (e.g., "<-[r:TYPE]-").
    
    Returns:
        A tuple containing the direction ("INCOMING", "OUTGOING", or "BIDIRECTIONAL")
        and a list of relation type strings.
    """
    relation_direction = judge_direction(str_relation)        
    relation_type = RELATION_TYPE_PATTERN.search(str_relation)
    if relation_type is None or relation_type.group('relation_type') is None:
        return relation_direction, []
    relation_types = [t.strip().strip('!') for t in relation_type.group('relation_type').split("|")]
    return relation_direction, relation_types
