
# Define the actors
actor User {}

# Define the resources
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
  relations = {
    creator: User,
    organization: Organization
  };
  "read" if "editor";
  "read" if "reader";
  "edit" if "editor";

  # Rules for ABAC
  "reader" if "admin" on "organization";
  "editor" if "admin" on "organization";
  "read" if "member" on "organization" and not is_private(resource);
}

# Define the attribute "is_private"
is_private(doc: Documents) if doc.is_private = true;

# Tests
test "Admins can read and edit any document" {
  setup {
    has_role(User{"Alice"}, "admin", Organization{"Org1"});
    has_relation(Documents{"Doc1"}, "organization", Organization{"Org1"});
  }
  assert allow(User{"Alice"}, "read", Documents{"Doc1"});
  assert allow(User{"Alice"}, "edit", Documents{"Doc1"});
}

test "Members cannot read a private document" {
  setup {
    has_role(User{"Bob"}, "member", Organization{"Org1"});
    has_relation(Documents{"Doc2"}, "organization", Organization{"Org1"});
    Documents{"Doc2"}.is_private = true;
  }
  assert_not allow(User{"Bob"}, "read", Documents{"Doc2"});
}
