/**
 * @license
 * The MIT License (MIT)
 * Copyright 2015 Government of Canada
 *
 * @author
 * Ian Boyes
 *
 * @exports ManageViruses
 */

'use strict';

var _ = require('lodash');
import React from "react";

var Add = require('./Manage/Add');
var Detail = require('./Manage/Detail');
var Export = require('./Manage/Export');
var Import = require('./Manage/Import');
var Toolbar = require('./Manage/Toolbar');

var Icon = require('virtool/js/components/Base/Icon');
var VirusList = require("./Manage/List");
var VirusToolbar = require("./Manage/Toolbar");
var DetailModal = require('virtool/js/components/Base/DetailModal');

/**
 * A main window component used for viewing all viruses in the reference database and adding new viruses via a modal
 * form.
 *
 * @class
 */
var ManageViruses = React.createClass({

    getInitialState: function () {
        return {
            documents: dispatcher.db.viruses.chain(),

            findTerm: "",
            modifiedOnly: false,
            sortTerm: "name",
            sortDescending: false
        };
    },

    componentDidMount: function () {
        dispatcher.db.viruses.on("change", this.update);
    },

    componentWillUnmount: function () {
        dispatcher.db.viruses.off("change", this.update);
    },

    setFindTerm: function (event) {
        this.setState({
            findTerm: event.target.value || ""
        });
    },

    setSortTerm: function (term) {
        this.setState({
            sortTerm: term,
            sortDescending: this.state.sortTerm
        });
    },

    toggleModifiedOnly: function () {
        this.setState({
            modifiedOnly: !this.state.modifiedOnly
        });
    },

    update: function () {
        this.setState({
            documents: dispatcher.db.viruses.chain()
        });
    },

    /**
     * Hides the virus detail modal. Triggered by called the onHide prop function within the modal.
     *
     * @func
     */
    hideModal: function () {
        dispatcher.router.clearExtra();
    },

    render: function () {

        var documents = this.state.documents.branch();

        if (this.state.modifiedOnly) {
            documents = documents.find({modified: true});
        }

        if (this.state.findTerm) {
            var test = {$regex: [this.state.findTerm, "i"]};

            documents = documents.find({$or: [
                {name: test},
                {abbreviation: test}
            ]});
        }

        documents = documents.simplesort(this.state.sortTerm).data();

        return (
            <div>
                <VirusToolbar
                    onChange={this.setFindTerm}
                    modifiedOnly={this.state.modifiedOnly}
                    toggleModifiedOnly={this.toggleModifiedOnly}
                />

                <VirusList
                    route={this.props.route}
                    documents={documents}
                    canArchive={this.state.canArchive}
                />

                <Add show={this.props.route.extra[0] === "add"} onHide={this.hideModal} />

                <Export show={this.props.route.extra[0] === "export"} onHide={this.hideModal} />

                <Import show={this.props.route.extra[0] === "import"} onHide={this.hideModal} />
            </div>
        );
    }
});

module.exports = ManageViruses;