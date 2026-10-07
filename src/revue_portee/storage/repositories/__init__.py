"""Table access for one project database. Functions take an open connection, so that
a use case can group several writes (and its journal entry) in one transaction."""
