actor User {}

resource Organization {
  roles = ["admin", "member"];
  permissions = ["read", "write"];
  relations = { documents: Documents };

  # Role implication, if needed
  "member" if "admin";
}

resource Documents {
  roles = ["reader", "editor"];
  permissions = ["read", "edit"];
  relations = { creator: User, organization: Organization };

  # Editors are also readers by implication
  "read" if "editor";

  # Allow admin of org to read & edit any document in org
  "read" if is_admin_of_organization(actor, resource);
  "edit" if is_admin_of_organization(actor, resource);

  # Allow member of org to read doc if not private
  "read" if is_member_of_organization(actor, resource) and is_private(resource);
}

# Helper: true if actor is admin for this doc's organization
is_admin_of_organization(actor: User, document: Documents) if
  org matches Organization and
  has_relation(document, "organization", org) and
  has_role(actor, "admin", org);

# Helper: true if actor is member for this doc's organization
is_member_of_organization(actor: User, document: Documents) if
  org matches Organization and
  has_relation(document, "organization", org) and
  has_role(actor, "member", org);

# Optional: attribute check for is_private
is_private(doc: Documents) if
  get_attribute(doc, "is_private") = true;