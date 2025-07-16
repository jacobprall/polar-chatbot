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
  
  # Organization admin permissions on documents
  "read" if "admin" on "organization";
  "edit" if "admin" on "organization";

  # Members can read documents if not is_private
  "read" if "member" on "organization" and not is_private(resource);
}

# Attribute accessor stub for is_private flag on Documents
is_private(_doc: Documents) if Boolean{true};
is_private(_doc: Documents) if Boolean{false};

test "org admin can read and edit all org docs" {
  setup {
    has_role(User{"alice"}, "admin", Organization{"org1"});
    has_relation(Documents{"doc1"}, "organization", Organization{"org1"});
    has_relation(Documents{"doc2"}, "organization", Organization{"org1"});
    is_private(Documents{"doc1"}, Boolean{false});
    is_private(Documents{"doc2"}, Boolean{true});
  }
  assert allow(User{"alice"}, "read", Documents{"doc1"});
  assert allow(User{"alice"}, "edit", Documents{"doc1"});
  assert allow(User{"alice"}, "read", Documents{"doc2"});
  assert allow(User{"alice"}, "edit", Documents{"doc2"});
}

test "org member can read only non-private docs" {
  setup {
    has_role(User{"bob"}, "member", Organization{"org1"});
    has_relation(Documents{"doc1"}, "organization", Organization{"org1"});
    has_relation(Documents{"doc2"}, "organization", Organization{"org1"});
    is_private(Documents{"doc1"}, Boolean{false});
    is_private(Documents{"doc2"}, Boolean{true});
  }
  assert allow(User{"bob"}, "read", Documents{"doc1"});
  assert_not allow(User{"bob"}, "edit", Documents{"doc1"});
  assert_not allow(User{"bob"}, "read", Documents{"doc2"});
  assert_not allow(User{"bob"}, "edit", Documents{"doc2"});
}

test "member cannot read docs for other orgs" {
  setup {
    has_role(User{"carol"}, "member", Organization{"org1"});
    has_relation(Documents{"doc3"}, "organization", Organization{"org2"});
    is_private(Documents{"doc3"}, Boolean{false});
  }
  assert_not allow(User{"carol"}, "read", Documents{"doc3"});
  assert_not allow(User{"carol"}, "edit", Documents{"doc3"});
}