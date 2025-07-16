actor User {}

resource Organization {
  roles = ["admin", "member"];
  permissions = ["read", "write"];
  relations = { documents: Documents };

  # Permissions assignments for organization
  "read" if "member";
  "write" if "admin";
}

resource Documents {
  roles = ["reader", "editor"];
  permissions = ["read", "edit"];
  relations = { creator: User, organization: Organization };

  # Users who are admins of the organization can read and edit all documents
  "read" if "admin" on "organization";
  "edit" if "admin" on "organization";

  # Users who are members of an organization can read documents only if is_private = false
  "read" if
    "member" on "organization" and
    is_private(resource, Boolean{false});
}

# Example facts for is_private attribute.
# In a real system, these would be supplied as data.
is_private(Documents{"public1"}, Boolean{false});
is_private(Documents{"private1"}, Boolean{true});

# Test
test "admins and members organization document access" {
  setup {
    has_role(User{"alice"}, "admin", Organization{"acme"});
    has_role(User{"bob"}, "member", Organization{"acme"});
    has_relation(Documents{"public1"}, "organization", Organization{"acme"});
    has_relation(Documents{"private1"}, "organization", Organization{"acme"});
  }

  # Admins can read and edit all docs
  assert allow(User{"alice"}, "read", Documents{"public1"});
  assert allow(User{"alice"}, "edit", Documents{"public1"});
  assert allow(User{"alice"}, "read", Documents{"private1"});
  assert allow(User{"alice"}, "edit", Documents{"private1"});

  # Members can read only public docs, never edit
  assert allow(User{"bob"}, "read", Documents{"public1"});
  assert_not allow(User{"bob"}, "read", Documents{"private1"});
  assert_not allow(User{"bob"}, "edit", Documents{"public1"});
  assert_not allow(User{"bob"}, "edit", Documents{"private1"});
}
