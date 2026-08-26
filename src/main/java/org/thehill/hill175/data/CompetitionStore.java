package org.thehill.hill175.data;

import org.thehill.hill175.model.Account;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.model.Entry;

import java.util.Collection;
import java.util.Optional;
import java.util.UUID;

public interface CompetitionStore {
    Optional<Account> account(String nicknameKey);

    void saveAccount(Account account);

    Optional<Entry> entry(UUID id);

    Collection<Entry> entries();

    void saveEntry(Entry entry);

    void deleteEntry(UUID id);

    int nextAllocation(Category category);

    void recordConnection(String nicknameKey, String address, String event);

    void flush();
}
