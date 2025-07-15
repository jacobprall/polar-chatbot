actor User {}

resource Organization {
  roles = ["admin", "member"];
  permissions = ["read", "write"];
  relations = { documents: Documents };

  # admin can read and write
  "read" if "admin";
  "write" if "admin";

  # member can read
  "read" if "member";
}

resource Documents {
  roles = ["reader", "editor"];
  permissions = ["read", "edit"];
  relations = { creator: User, organization: Organization };

  # direct document-level reader/editor
  "read" if "reader";
  "edit" if "editor";

  # admin of org can read and edit all docs in org
  "read" if "admin" on "organization";
  "edit" if "admin" on "organization";

  # member of org can read doc only if it's not private
  "read" if "member" on "organization" and not is_private(resource);
}

is_private(doc: Documents) if
  doc.is_private = Boolean{true};
