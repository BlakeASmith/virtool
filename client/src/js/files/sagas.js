import { noop } from "lodash-es";
import { buffers, END, eventChannel } from "redux-saga";
import { call, put, take, takeEvery, takeLatest } from "redux-saga/effects";
import * as filesAPI from "./api";
import { putGenericError, setPending, apiCall } from "../sagaUtils";
import { LIST_FILES, REMOVE_FILE, UPLOAD } from "../actionTypes";
import { uploadProgress } from "./actions";

export function* watchFiles () {
    yield takeLatest(LIST_FILES.REQUESTED, listFiles);
    yield takeEvery(REMOVE_FILE.REQUESTED, removeFile);
    yield takeEvery(UPLOAD.REQUESTED, upload);
}

export function* listFiles (action) {
    yield apiCall(filesAPI.list, action, LIST_FILES, {fileType: action.fileType});
}

export function* removeFile (action) {
    yield setPending(apiCall(filesAPI.remove, action, REMOVE_FILE));
}

export function* upload (action) {

    const { file, fileType, localId } = action;

    const channel = yield call(createUploadChannel, file, fileType);

    while (true) {
        const { progress = 0, response, err } = yield take(channel);

        if (err) {
            return yield putGenericError(UPLOAD, err);
        }

        if (response) {
            return yield put({type: UPLOAD.SUCCEEDED, data: response.body});
        }

        yield put(uploadProgress(localId, progress));
    }
}

const createUploadChannel = (file, fileType) => (
    eventChannel(emitter => {
        const onProgress = (e) => {
            if (e.lengthComputable) {
                emitter({progress: e.percent});
            }
        };

        const onSuccess = (response) => {
            emitter({response});
            emitter(END);
        };

        const onFailure = (err) => {
            emitter({err});
            emitter(END);
        };

        filesAPI.upload(
            file,
            fileType,
            onProgress,
            onSuccess,
            onFailure
        );

        return noop;
    }, buffers.sliding(2))
);
