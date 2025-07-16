actor User {}

resource Organization {
  roles = ["admin", "member"];
  permissions = ["read", "write"];
  relations = { documents: Documents };

  # permissions not used for document access
}

resource Documents {
  roles = ["reader", "editor"];
  permissions = ["read", "edit"];
  relations = { creator: User, organization: Organization };

  # admins of organization can read all docs in that org
  "read" if "admin" on "organization";
  "edit" if "admin" on "organization";

  # members of organization can read only if doc is not private
  "read" if "member" on "organization" and is_private(resource, false);

  # editor can edit document
  "edit" if "editor";
  # reader can read document
  "read" if "reader";
}

# tests
test "admins of org can read and edit all org documents" {
  setup {
    has_role(User{"alice"}, "admin", Organization{"org1"});
    has_relation(Documents{"doc1"}, "organization", Organization{"org1"});
  }
  assert allow(User{"alice"}, "read", Documents{"doc1"});
  assert allow(User{"alice"}, "edit", Documents{"doc1"});
}

test "members can read non-private documents only" {
  setup {
    has_role(User{"bob"}, "member", Organization{"org1"});
    has_relation(Documents{"doc2"}, "organization", Organization{"org1"});
    is_private(Documents{"doc2"}, false);
    has_relation(Documents{"doc3"}, "organization", Organization{"org1"});
    is_private(Documents{"doc3"}, true);
  }
  assert allow(User{"bob"}, "read", Documents{"doc2"});
  assert_not allow(User{"bob"}, "read", Documents{"doc3"});
}

test "members cannot edit through org role" {
  setup {
    has_role(User{"bob"}, "member", Organization{"org1"});
    has_relation(Documents{"doc2"}, "organization", Organization{"org1"});
  }
  assert_not allow(User{"bob"}, "edit", Documents{"doc2"});
}

test "editor can edit document regardless of org membership" {
  setup {
    has_role(User{"eve"}, "editor", Documents{"doc4"});
  }
  assert allow(User{"eve"}, "edit", Documents{"doc4"});
  assert_not allow(User{"eve"}, "read", Documents{"doc4"});
}