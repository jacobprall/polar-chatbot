actor User {}

resource Organization {
  roles = ["admin", "member"];
  permissions = ["read", "write"];
  relations = { documents: Documents };

  # (No org-specific rules required based on requirements)
}

resource Documents {
  roles = ["reader", "editor"];
  permissions = ["read", "edit"];
  relations = { creator: User, organization: Organization };

  # Org admins can read & edit ALL documents related to their org
  "read" if is_org_admin(actor, resource);
  "edit" if is_org_admin(actor, resource);

  # Org members can read documents that aren't private
  "read" if is_org_member(actor, resource) and not is_private(resource);

  # Editors can edit
  "edit" if "editor";
}

# Helper: is user an admin of the document's organization?
is_org_admin(user: User, document: Documents) if
  org matches Organization and
  has_relation(document, "organization", org) and
  has_role(user, "admin", org);

# Helper: is user a member of the document's organization?
is_org_member(user: User, document: Documents) if
  org matches Organization and
  has_relation(document, "organization", org) and
  has_role(user, "member", org);

# Attribute check, expected in app logic
is_private(document: Documents) if
  document.is_private = Boolean{true};