
actor User {
}

resource Organization {
  roles = ["admin", "member"];
  permissions = ["read", "write"];
  relations = { documents: Documents };
  
  "read" if "admin";
  "write" if "admin";
}

resource Documents {
  roles = ["reader", "editor"];
  permissions = ["read", "edit"];
  relations = { creator: User, organization: Organization };
  "read" if "editor";
  
  "read" if "admin" on "organization";
  "edit" if "admin" on "organization";
  
  "read" if "reader" and not is_private(resource);
}
