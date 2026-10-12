"""GraphQL documents for the PR draft-state mutations (no REST equivalent)."""

_MARK_READY_MUTATION = """
mutation($id: ID!) {
  markPullRequestReadyForReview(input: {pullRequestId: $id}) {
    pullRequest {
      number
      isDraft
      url
    }
  }
}
"""

_CONVERT_TO_DRAFT_MUTATION = """
mutation($id: ID!) {
  convertPullRequestToDraft(input: {pullRequestId: $id}) {
    pullRequest {
      number
      isDraft
      url
    }
  }
}
"""
