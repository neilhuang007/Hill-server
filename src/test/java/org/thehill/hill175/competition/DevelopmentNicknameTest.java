package org.thehill.hill175.competition;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class DevelopmentNicknameTest {
    @Test
    void acceptsActualJavaAndPrefixedBedrockNamesWithoutConfusingThem() {
        assertTrue(CompetitionModule.matchesDevelopmentNickname("JavaBuilder", "JavaBuilder"));
        assertTrue(CompetitionModule.matchesDevelopmentNickname(".BedrockBuilder1234", ".BedrockBuilder1234"));
        assertTrue(CompetitionModule.matchesDevelopmentNickname(".bedrockbuilder", ".BedrockBuilder"));
        assertFalse(CompetitionModule.matchesDevelopmentNickname("BedrockBuilder", ".BedrockBuilder"));
        assertFalse(CompetitionModule.matchesDevelopmentNickname(".SomeoneElse", ".BedrockBuilder"));
    }

    @Test
    void rejectsMalformedNamesEvenWhenTheyMatch() {
        for (String invalid : new String[]{"", "a b", "a\nb", "x".repeat(65)}) {
            assertFalse(CompetitionModule.matchesDevelopmentNickname(invalid, invalid));
        }
        assertFalse(CompetitionModule.matchesDevelopmentNickname(null, "Builder"));
    }
}
