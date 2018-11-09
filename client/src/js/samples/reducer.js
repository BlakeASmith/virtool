import { xor } from "lodash-es";
import {
    WS_INSERT_SAMPLE,
    WS_UPDATE_SAMPLE,
    WS_REMOVE_SAMPLE,
    FIND_SAMPLES,
    GET_SAMPLE,
    UPDATE_SAMPLE,
    REMOVE_SAMPLE,
    UPDATE_SAMPLE_RIGHTS,
    SHOW_REMOVE_SAMPLE,
    HIDE_SAMPLE_MODAL,
    FIND_READ_FILES,
    FIND_READY_HOSTS,
    SELECT_SAMPLE,
    CLEAR_SAMPLE_SELECTION
} from "../app/actionTypes";
import { updateDocuments, insert, update, remove } from "../utils/reducers";

export const initialState = {
    documents: null,
    term: "",
    page: 0,
    detail: null,
    readFiles: null,
    showEdit: false,
    showRemove: false,
    editError: false,
    reservedFiles: [],
    readyHosts: null,
    selected: []
};

export default function samplesReducer(state = initialState, action) {
    switch (action.type) {
        case WS_INSERT_SAMPLE:
            return insert(state, action, "created_at", true);

        case WS_UPDATE_SAMPLE:
            return update(state, action);

        case WS_REMOVE_SAMPLE:
            return remove(state, action);

        case FIND_SAMPLES.REQUESTED:
            return { ...state, term: action.term };

        case FIND_SAMPLES.SUCCEEDED:
            return updateDocuments(state, action);

        case FIND_READ_FILES.SUCCEEDED:
            return { ...state, readFiles: action.data.documents };

        case FIND_READY_HOSTS.SUCCEEDED:
            return { ...state, readyHosts: action.data.documents };

        case GET_SAMPLE.REQUESTED:
            return { ...state, detail: null };

        case GET_SAMPLE.SUCCEEDED:
            return { ...state, detail: action.data };

        case UPDATE_SAMPLE.SUCCEEDED:
            return { ...state, detail: { ...state.detail, ...action.data } };

        case UPDATE_SAMPLE_RIGHTS.SUCCEEDED:
            return { ...state, detail: { ...state.detail, ...action.data } };

        case REMOVE_SAMPLE.SUCCEEDED:
            return { ...state, detail: null };

        case SHOW_REMOVE_SAMPLE:
            return { ...state, showRemove: true };

        case HIDE_SAMPLE_MODAL:
            return { ...state, showRemove: false };

        case SELECT_SAMPLE:
            return {
                ...state,
                selected: xor(state.selected, [action.sampleId])
            };

        case CLEAR_SAMPLE_SELECTION:
            return {
                ...state,
                selected: []
            };

        default:
            return state;
    }
}
