actor User {}

resource Organization {
  roles = ["admin", "member"];
  permissions = ["read", "write"];
  relations = { documents: Documents };
}

resource Documents {
  roles = ["reader", "editor"];
  permissions = ["read", "edit"];
  relations = { creator: User, organization: Organization };

  # All admins of organization can read and edit all documents in it
  "read" if "admin" on "organization";
  "edit" if "admin" on "organization";

  # Members of org can read, if not private
  "read" if "member" on "organization" and not is_private(resource);
}

# This attribute rule must be implemented as data or in the host
# Example implementation for test purposes:
is_private(Documents{"doc1"}) if Boolean{true};
is_private(Documents{"doc2"}) if Boolean{false};

# TESTS

test "Org admins can read and edit any document" {
  setup {
    has_role(User{"alice"}, "admin", Organization{"org1"});
    has_relation(Documents{"doc1"}, "organization", Organization{"org1"});
    has_relation(Documents{"doc2"}, "organization", Organization{"org1"});
  }
  assert allow(User{"alice"}, "read", Documents{"doc1"});
  assert allow(User{"alice"}, "edit", Documents{"doc1"});
  assert allow(User{"alice"}, "read", Documents{"doc2"});
  assert allow(User{"alice"}, "edit", Documents{"doc2"});
}

test "Org members can read public documents" {
  setup {
    has_role(User{"bob"}, "member", Organization{"org1"});
    has_relation(Documents{"doc2"}, "organization", Organization{"org1"});
  }
  assert allow(User{"bob"}, "read", Documents{"doc2"});
}

test "Org members cannot read private documents" {
  setup {
    has_role(User{"carol"}, "member", Organization{"org1"});
    has_relation(Documents{"doc1"}, "organization", Organization{"org1"});
  }
  assert_not allow(User{"carol"}, "read", Documents{"doc1"});
}

test "Org members cannot edit documents" {
  setup {
    has_role(User{"dave"}, "member", Organization{"org1"});
    has_relation(Documents{"doc2"}, "organization", Organization{"org1"});
  }
  assert_not allow(User{"dave"}, "edit", Documents{"doc2"});
}