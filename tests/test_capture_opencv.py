from elp_console.capture_opencv import candidate_indices


def test_opencv_candidates_try_selected_index_first_without_duplicates():
    assert candidate_indices(1, (0, 1, 2, 1)) == (1, 0, 2)
