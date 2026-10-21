"""Opaque hash-valid graph fields still need safe legacy presentation shapes."""

import pytest
import test_artifact_graph as graph_tests

from agent_rewind.artifact_metadata import ArtifactError
from agent_rewind.legacy_graph_views import GraphPresentation

graph = graph_tests.graph


@pytest.mark.parametrize(
    "changes",
    [
        [None],
        ["changed"],
        [{"path": "file"}],
        [{"path": "../file", "change": "added"}],
        [{"path": "file", "change": "unknown"}],
        [{"path": "file", "change": []}],
        [{"path": "file", "change": "added", "extra": True}],
        [{"path": "x" * 513, "change": "added"}],
        [{"path": "file", "change": "added"}, {"path": "file", "change": "removed"}],
    ],
)
def test_hash_valid_opaque_changes_refuse_unsupported_presentation(graph, changes):
    root, blobs = graph

    def mutate(index, event):
        event["changes"] = changes

    graph_tests.rewrite_events(root, blobs, mutate)
    verified = graph_tests.verify(root, blobs)
    with pytest.raises(ArtifactError, match="artifact_graph_invalid"):
        GraphPresentation(verified, 64 * 1024 * 1024)
