package org.thehill.hill175.model;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CategoryTest {
    @Test
    void parsesCompetitionCategoryNamesCaseInsensitively() {
        assertEquals(Category.JOURNEY, Category.parse("journey").orElseThrow());
        assertEquals(Category.PLACE, Category.parse("PLACE").orElseThrow());
        assertEquals(Category.PEOPLE, Category.parse(" People ").orElseThrow());
        assertTrue(Category.parse("unknown").isEmpty());
    }
}
