"""
This module provides functionality for defining and loading graph schemas for Cypher queries.
It defines the Schema namedtuple and provides a function to parse schema definitions from a string.
"""

import re
from collections import namedtuple
from typing import List

Schema = namedtuple("Schema", ["left_node", "relation", "right_node"])

def load_schemas(str_schemas: str) -> List[Schema]:
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
